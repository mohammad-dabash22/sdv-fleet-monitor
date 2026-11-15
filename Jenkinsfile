// CI/CD for the SDV Fleet Monitor: test, build the images, roll the mock
// dashboard and the real cloud (Zenoh router + cloud service + PostgreSQL) out on
// GKE, record the rollout, print the public URLs.
//
// Runs on every new commit on main: GitHub's push webhook if the repository has
// one, and otherwise Jenkins checks GitHub every two minutes.
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

    triggers {
        githubPush()
        pollSCM('H/2 * * * *')
    }

    // The streaming Dataflow job costs credits while it runs, so it is never started by a merge (spec D-7):
    // run "Build with Parameters" and pick start before a demo, drain right after (D-16).
    parameters {
        choice(name: 'DATAFLOW', choices: ['none', 'start', 'drain'],
               description: 'none: normal build. start/drain: the streaming Dataflow job (tools/dataflow_job.py)')
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
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    // Cloud Build, not docker push: Cloud Shell's IPv4 route to
                    // Artifact Registry is broken.
                    sh 'gcloud builds submit --config cloudbuild.yaml --substitutions _IMAGE="$IMAGE" . --suppress-logs'
                    sh 'gcloud builds submit -t "$DB_IMAGE" deploy/cicd-db --suppress-logs'
                }
            }
        }

        stage('database') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    sh 'gcloud container clusters get-credentials "$CLUSTER" --region="$CLUSTER_REGION"'
                    sh 'sed "s|IMAGE_PLACEHOLDER|${DB_IMAGE}|" deploy/k8s/cicd-db.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-cicd-db --timeout=300s'
                }
            }
        }

        // V1 data pipeline (spec REQ-037 AC1): the two Pub/Sub topics and the subscriptions the Dataflow
        // job reads. Idempotent: each is created only when missing. A failure here (for example, no
        // Pub/Sub permission for the Jenkins service account yet) marks the build UNSTABLE but does not
        // stop the deploy below: the live system does not depend on Pub/Sub.
        stage('pubsub') {
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'FAILURE') {
                    container('gcloud') {
                        sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                        sh 'gcloud config set project "$PROJECT"'
                        sh '''
                            for kind in telemetry hazards; do
                                gcloud pubsub topics describe "fleet-$kind" >/dev/null 2>&1 \
                                    || gcloud pubsub topics create "fleet-$kind"
                                gcloud pubsub subscriptions describe "fleet-$kind-beam" >/dev/null 2>&1 \
                                    || gcloud pubsub subscriptions create "fleet-$kind-beam" --topic "fleet-$kind" \
                                           --message-retention-duration=1h
                            done
                        '''
                    }
                }
            }
        }

        stage('deploy') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    sh 'gcloud container clusters get-credentials "$CLUSTER" --region="$CLUSTER_REGION"'
                    // apply, not delete + create, so the external IP survives.
                    sh 'sed "s|IMAGE_PLACEHOLDER|${IMAGE}|" deploy/k8s/dashboard.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-dashboard --timeout=300s'
                    // The real cloud: fleet PostgreSQL (its secret is created once by hand,
                    // see fleet-db.yaml), then the Zenoh router + cloud service, same image.
                    sh 'kubectl apply -f deploy/k8s/fleet-db.yaml'
                    sh 'kubectl rollout status deployment/sdv-fleet-db --timeout=300s'
                    sh 'sed "s|IMAGE_PLACEHOLDER|${IMAGE}|" deploy/k8s/cloud.yaml | kubectl apply -f -'
                    sh 'kubectl rollout status deployment/sdv-cloud --timeout=300s'
                }
            }
        }

        stage('record') {
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    sh 'gcloud container clusters get-credentials "$CLUSTER" --region="$CLUSTER_REGION"'
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
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    sh 'gcloud container clusters get-credentials "$CLUSTER" --region="$CLUSTER_REGION"'
                    // The load balancer takes a minute or two to get an IP the first time.
                    sh '''
                        for svc in sdv-dashboard sdv-cloud; do
                            IP=""
                            for i in $(seq 1 60); do
                                IP=$(kubectl get service/$svc \
                                     -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
                                [ -n "$IP" ] && break
                                sleep 5
                            done
                            if [ -z "$IP" ]; then
                                echo "The $svc load balancer had no external IP after 5 minutes."
                                kubectl describe service/$svc
                                exit 1
                            fi
                            echo "$svc: http://$IP"
                        done
                        echo "(sdv-dashboard = mock fleet, sdv-cloud = real vans over Zenoh)"
                    '''
                }
            }
        }

        // Only when DATAFLOW is start or drain (spec REQ-037 AC2): the same script as on a laptop.
        // The database URL comes from the existing secret, pointed at the internal load balancer, so the
        // password is never a build parameter.
        stage('dataflow') {
            when { expression { params.DATAFLOW != 'none' } }
            steps {
                container('gcloud') {
                    sh 'gcloud auth activate-service-account --key-file "$GCP_KEY"'
                    sh 'gcloud config set project "$PROJECT"'
                    sh 'gcloud container clusters get-credentials "$CLUSTER" --region="$CLUSTER_REGION"'
                    sh '''
                        python3 -m venv /tmp/dataflow && /tmp/dataflow/bin/pip install --quiet -r requirements.txt
                        export GOOGLE_APPLICATION_CREDENTIALS="$GCP_KEY"
                        if [ "$DATAFLOW" = start ]; then
                            IP=$(kubectl get service sdv-fleet-db-internal -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
                            DB_URL=$(kubectl get secret sdv-fleet-db -o jsonpath='{.data.DATABASE_URL}' | base64 -d \
                                     | sed "s|@sdv-fleet-db:|@$IP:|")
                            /tmp/dataflow/bin/python -m tools.dataflow_job start --project "$PROJECT" --db-url "$DB_URL"
                        else
                            /tmp/dataflow/bin/python -m tools.dataflow_job drain --project "$PROJECT"
                        fi
                    '''
                }
            }
        }
    }
}
