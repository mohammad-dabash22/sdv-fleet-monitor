// CI/CD for the SDV Fleet Monitor dashboard.
//
// On every commit: run the tests, build the images with Cloud Build, push them
// to Artifact Registry, roll the dashboard out on GKE, record the rollout in
// the deployment log, and print the public URL.
//
// Jenkins itself is installed from deploy/jenkins/values.yaml. It needs these
// five credentials, created once under Manage Jenkins -> Credentials:
//
//   sdv-gcp-key          Secret file   JSON key for the sdv-jenkins service account
//   sdv-project-id       Secret text   the GCP project id
//   sdv-repo-path        Secret text   e.g. us-central1-docker.pkg.dev/<project>/sdv-fleet
//   sdv-cluster-name     Secret text   e.g. sdv-fleet-cluster
//   sdv-cluster-region   Secret text   e.g. us-central1
//
// Job: New Item -> Pipeline -> Build Triggers: "GitHub hook trigger for GITScm
// polling" -> Pipeline script from SCM -> Script Path: Jenkinsfile.

pipeline {
    environment {
        GCP_KEY        = credentials('sdv-gcp-key')
        PROJECT        = credentials('sdv-project-id')
        REPO_PATH      = credentials('sdv-repo-path')
        CLUSTER        = credentials('sdv-cluster-name')
        CLUSTER_REGION = credentials('sdv-cluster-region')

        APP_NAME = 'sdv-fleet-dashboard'
        // Tagged with the build number, never :latest. With a fixed tag the
        // Deployment spec would not change between builds, kubectl apply would
        // report "unchanged", and the new image would never be rolled out.
        IMAGE = "$REPO_PATH/$APP_NAME:$BUILD_NUMBER"

        // The log database is tagged :latest on purpose, the opposite of the
        // dashboard. Its spec is then identical between builds, kubectl apply
        // reports "unchanged", and PostgreSQL is not restarted on every deploy.
        // Changing init.sql therefore does NOT reach a database that already
        // exists; that is a schema migration, which is a manual job anyway.
        DB_IMAGE = "$REPO_PATH/sdv-cicd-db:latest"
    }

    agent {
        // Two worker containers in one pod: python runs the tests, gcloud does
        // everything that talks to GCP.
        kubernetes {
            label 'sdv-fleet'
            yaml '''
apiVersion: v1
kind: Pod
metadata:
  labels:
    component: ci
spec:
  containers:
    - name: python
      image: python:3.12
      command: ["cat"]
      tty: true
      resources:
        requests:
          cpu: 500m
          memory: 1Gi
    - name: gcloud
      image: google/cloud-sdk:latest
      command: ["cat"]
      tty: true
      resources:
        requests:
          cpu: 500m
          memory: 1Gi
'''
        }
    }

    stages {
        stage('test') {
            steps {
                container('python') {
                    sh 'pip install --quiet -r requirements-dev.txt'
                    sh 'pytest -q'
                }
            }
        }

        stage('containerize') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $GCP_KEY'
                    sh 'gcloud config set project $PROJECT'
                    // Cloud Build, not docker push: Cloud Shell has no working
                    // IPv4 route to Artifact Registry and docker push fails there
                    // with "connection refused".
                    sh 'gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE=$IMAGE . --suppress-logs'
                    // deploy/cicd-db/ is self-contained, so the plain -t form works here.
                    sh 'gcloud builds submit -t $DB_IMAGE deploy/cicd-db --suppress-logs'
                }
            }
        }

        stage('database') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $GCP_KEY'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_REGION'
                    sh 'sed "s|IMAGE_PLACEHOLDER|$DB_IMAGE|" deploy/k8s/cicd-db.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-cicd-db --timeout=300s'
                }
            }
        }

        stage('deploy') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $GCP_KEY'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_REGION'
                    // apply, not delete + create: the Service and its external IP
                    // survive, so the demo URL stays the same across builds.
                    sh 'sed "s|IMAGE_PLACEHOLDER|$IMAGE|" deploy/k8s/dashboard.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-dashboard --timeout=300s'
                }
            }
        }

        stage('record') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $GCP_KEY'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_REGION'
                    // psql runs inside the database pod over its unix socket, so
                    // no password and no client library are needed out here.
                    sh '''
                        POD=$(kubectl get pod -l app=sdv-cicd-db -o jsonpath='{.items[0].metadata.name}')
                        kubectl exec "$POD" -- psql -U sdv_cicd -d sdv_cicd -q -c "INSERT INTO deployments (build_number, image, git_commit, branch) VALUES ($BUILD_NUMBER, '$IMAGE', '${GIT_COMMIT:-unknown}', '${GIT_BRANCH:-unknown}');"
                        echo "--- deployment history ---"
                        kubectl exec "$POD" -- psql -U sdv_cicd -d sdv_cicd -c "SELECT build_number, branch, left(git_commit, 7) AS commit, deployed_at FROM deployments ORDER BY id DESC LIMIT 10;"
                    '''
                }
            }
        }

        stage('service') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $GCP_KEY'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_REGION'
                    // The load balancer takes a minute or two to be given an IP
                    // the first time. On later builds it is already there.
                    sh '''
                        for i in $(seq 1 60); do
                            IP=$(kubectl get service/sdv-dashboard \
                                 -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
                            if [ -n "$IP" ]; then
                                echo "Dashboard and API: http://$IP"
                                exit 0
                            fi
                            sleep 5
                        done
                        echo "The load balancer had no external IP after 5 minutes."
                        kubectl describe service/sdv-dashboard
                        exit 1
                    '''
                }
            }
        }
    }
}
