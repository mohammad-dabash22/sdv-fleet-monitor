// CI/CD for the SDV Fleet Monitor dashboard: test, build the images, roll the
// dashboard out on GKE, record the rollout, print the public URL.
//
// Jenkins is installed from deploy/jenkins/values.yaml and needs five
// credentials: sdv-gcp-key (secret file), sdv-project-id, sdv-repo-path,
// sdv-cluster-name, sdv-cluster-region.

pipeline {
    environment {
        GCP_KEY        = credentials('sdv-gcp-key')
        PROJECT        = credentials('sdv-project-id')
        REPO_PATH      = credentials('sdv-repo-path')
        CLUSTER        = credentials('sdv-cluster-name')
        CLUSTER_REGION = credentials('sdv-cluster-region')

        APP_NAME = 'sdv-fleet-dashboard'
        // Build number, never :latest, or kubectl apply sees no change and
        // never rolls the new image out.
        IMAGE = "$REPO_PATH/$APP_NAME:$BUILD_NUMBER"

        // :latest on purpose, so applying it does not restart PostgreSQL every build.
        DB_IMAGE = "$REPO_PATH/sdv-cicd-db:latest"
    }

    agent {
        // python runs the tests, gcloud does everything that talks to GCP.
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
                    // Cloud Build, not docker push: Cloud Shell's IPv4 route to
                    // Artifact Registry is broken.
                    sh 'gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE=$IMAGE . --suppress-logs'
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
                    // apply, not delete + create, so the external IP survives.
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
                    // psql runs in the database pod over its unix socket: no password needed.
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
                    // The load balancer takes a minute or two to get an IP the first time.
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
