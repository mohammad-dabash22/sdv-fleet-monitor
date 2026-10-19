// CI/CD for the SDV Fleet Monitor dashboard.
//
// On every commit: run the tests, build the image with Cloud Build, push it to
// Artifact Registry, roll it out on GKE, and print the public URL.
//
// Jenkins setup is the one from Lab 3 Part 2, and this pipeline deliberately
// reuses the same five credential IDs, so a Jenkins that already ran that lab
// needs nothing new:
//
//   service_account   Secret file   the jenkins-sa JSON key
//   project_id        Secret text   the GCP project id
//   repo_path         Secret text   e.g. us-central1-docker.pkg.dev/<project>/<repo>
//   cluster_name      Secret text   e.g. autopilot-cluster-1
//   cluster_zone      Secret text   e.g. us-central1
//
// Job: New Item -> Pipeline -> Build Triggers: "GitHub hook trigger for GITScm
// polling" -> Pipeline script from SCM -> Script Path: Jenkinsfile.

pipeline {
    environment {
        SERVICE_ACCOUNT = credentials('service_account')
        PROJECT         = credentials('project_id')
        REPO_PATH       = credentials('repo_path')
        CLUSTER         = credentials('cluster_name')
        CLUSTER_ZONE    = credentials('cluster_zone')

        APP_NAME = 'sdv-fleet-dashboard'
        // Tagged with the build number, never :latest. With a fixed tag the
        // Deployment spec would not change between builds, kubectl apply would
        // report "unchanged", and the new image would never be rolled out.
        IMAGE = "$REPO_PATH/$APP_NAME:$BUILD_NUMBER"
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
                    sh 'gcloud auth activate-service-account --key-file $SERVICE_ACCOUNT'
                    sh 'gcloud config set project $PROJECT'
                    // Cloud Build, not docker push: Cloud Shell has no working
                    // IPv4 route to Artifact Registry and docker push fails there
                    // with "connection refused".
                    sh 'gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE=$IMAGE . --suppress-logs'
                }
            }
        }

        stage('deploy') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $SERVICE_ACCOUNT'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_ZONE'
                    // apply, not delete + create: the Service and its external IP
                    // survive, so the demo URL stays the same across builds.
                    sh 'sed "s|IMAGE_PLACEHOLDER|$IMAGE|" deploy/k8s/dashboard.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-dashboard --timeout=300s'
                }
            }
        }

        stage('service') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file $SERVICE_ACCOUNT'
                    sh 'gcloud config set project $PROJECT'
                    sh 'gcloud container clusters get-credentials $CLUSTER --region=$CLUSTER_ZONE'
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
