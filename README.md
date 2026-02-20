# RepairAgent Replication Study

The RepairAgent Replication Project is an undergraduate research effort to replicate and extend a large language model based automated program repair (APR) coding agent from *[RepairAgent: An Autonomous, LLM-Based Agent for Program Repair (ICSE 2023)](https://arxiv.org/abs/2403.17134)*. The original work is a highly cited study evaluated on over 800 real world bugs from the Defects4J dataset. RepairAgent is powered by the OpenAI Chat Completions API and integrates coding tools to autonomously diagnose and repair software defects. 

This version runs on the National Research Platform (NRP) Nautilus Kubernetes cluster, which enables parallel execution of RepairAgent across individual bugs, reducing total experimentation time by months. The code is baked into a Docker image and the logs / data are output to a PVC with a back up sync to an S3 bucket. 

## Step 1: Set default namespace

Set the default namespace in Kubernetes, which allows you to not have to specify the namespace in the rest of the kubectl commands.

Run:

`kubectl config set-context nautilus --namespace=cal-poly-humboldt-repair-agent`

Double check default namespace with: 

`kubectl config view --minify --output 'jsonpath={..namespace}'`

## Step 2: Add API key to secrets

The RepairAgent requires an API key. Rather than using the .env baked into the image, we use Kubernetes Secrets. There are many ways to configure a job to access a secret. Since we only have a single API key, we are using env vars (envFrom: secretRef). 

First, create a the .env file and put it in the project root. 

Confirm .env is in both the .Dockerignore and .gitignore.

The only variable in the .env is the API key. Add:

`OPENAI_API_KEY=put-your-key-here`

Then, add the API key as secret to the namespace by running this from repair_agent/ where .env exists:

`kubectl create secret generic repairagent-env --from-env-file=.env`

Check whether secret was successfully created:

`kubectl get secret`

If you update .env, then re-run the create secret command with

```
kubectl create secret generic repairagent-env \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Step 3: Add S3 keys to secrets

1. Log in to nrp.ai 
2. Go to https://nrp.ai/s3token/ and request a token. An email will be sent to the email on your NRP account.
3. Open the email and follow the provided link in to see S3 credentials.
4. Add secrets to namespace by replacing "akey" and "skey" respectively in the following command: 

`kubectl create secret generic s3-creds --from-literal=AWS_ACCESS_KEY_ID=akey --from-literal=AWS_SECRET_ACCESS_KEY=skey`


## Step 4: Pre-Download tiktoken cache

This step is to prevent an NRP Nautilus-specific failure which restricts the outgoing request to download the tiktoken cache. We will pre-download it. 

Go to Downloads folder (or any local folder) and create a temporary venv there: 

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install tiktoken
```

While still in the venv, run this to stash the cache locally:

```bash
mkdir -p /tmp/tiktoken_cache
TIKTOKEN_CACHE_DIR=/tmp/tiktoken_cache python - <<'PY'
import tiktoken
tiktoken.get_encoding("cl100k_base")
PY
```

You will copy this into the PVC in the next step. Tiktoken knows about the cache because we are setting TIKTOKEN_CACHE_DIR is set in the environment.

## Step 5: Create and populate PVC

While in deployment directory in the terminal, create the PVC instance with: 

`kubectl create -f pvc-repairagent.yaml`

Double check with: 

`kubectl get pvc`

Make sure to mount BOTH the repairagent job pod AND the PVC helper pod to /app/repair_agent/experimental_setups/experiment_1/ using the volume_helper_pod.yaml, create the child directories that the RepairAgent expects when outputting logs. Note: There does not have to be an experiment_1/ directory in the image. You just need to make sure the `experiments_list.txt` (which is baked into the image) only says experiment_1 and that `increment_experiment.py` is not called in `run_on_defects4j.sh`. 

To create the helper pod that will allow you to see the PVC, run: 

`kubectl create -f pod-storage-helper.yaml`

For some reason, this is sometimes slow to spin up. Check the status with:

`kubectl get pod`

Copy /tmp/tiktoken_cache into the PVC using the helper pod with: 

`kubectl cp /tmp/tiktoken_cache pod-storage-helper:/app/repair_agent/experimental_setups/experiment_1/tiktoken_cache`

Enter the interactive shell to check that the folder was copied successfully:

`kubectl exec -it pod-storage-helper -- /bin/sh`

`CTRL + D` to exit the interactive shell. 

While the PVC allows readWriteMany, it's good practice to delete the pod after you're done:

`kubectl delete pod pod-storage-helper`

## Step 6: Create S3 Bucket with Helper Pod

There are several ways to access the Nautilus S3 instance, but one simple way is by accessing the endpoint through an S3 helper pod. The endpoint is defined in the pod with the key value pair: `name: RCLONE_CONFIG_NAUTILUS_ENDPOINT` and `value: "http://rook-ceph-rgw-nautiluss3.rook"`. We will use `s3-transfer-pod.yaml` which references the S3 secret keys we just added and the endpoint. 

`kubectl create -f pod-storage-helper.yaml`

Shell into the pod where you will be able to use `rclone` commands directly:

`kubectl exec -it pod-storage-helper -- sh`

Use this command to get the name of the S3 remote, which should be `nautilus`: 

`rclone listremotes`

You will see "2026/01/25 00:16:06 NOTICE: Config file "/config/rclone/rclone.conf" not found - using defaults", but this is expected since we are configuring rclone entirely through environment variables, not via a config file.

Create a permanent s3 bucket in the ceph west pool to store your data by using rclone inside the pod: 

`rclone mkdir nautilus:repair-agent-bucket`

Use this rclone to see if the bucket has been created in the nautilus remote:

`rclone lsd nautilus:repair-agent-bucket`

`rclone lsd nautilus:repair-agent-bucket/Chart_1`

Note: While the `job-repairagent-S3.yaml` will sometimes sync to an S3 path called `nautilus:repair-agent-bucket/failed/`, you do not have to create failed/ because S3 does not have directories, but rather prefixes that look like directory paths. If that part of the job runs, then it will just create objects with those prefixes.

List objects in bucket to confirm that the bucket is empty except for failed/: 

`rclone ls nautilus:repair-agent-bucket`


## Optional: Build and push Docker image

If you make any changes to the code, then you need to create your own Docker image to use in the Kubernetes job.

Go to the GitLab repo for the project. In the side bar, hover over "Deploy" then choose "Container registry". That will take you to the UI for the repo's container.

Log in to GitLab:

`docker login gitlab-registry.nrp-nautilus.io`

Make sure Docker Desktop is running if on Mac or Windows. Then from the root directory, build the image for Linux AMD arch (update tag as needed):

`docker buildx build --platform linux/amd64 -f Dockerfile.replication -t gitlab-registry.nrp-nautilus.io/humboldt/repairagent:0.11 --load .`

Optionally, check image size:

`docker images | grep repairagent`

Once you see "successfully built", push the image to the registry. Again, adjust the tag as needed. 

`docker push gitlab-registry.nrp-nautilus.io/humboldt/repairagent:0.11`

## Step 7: Set up bugs_list.txt in a ConfigMap

Copy and paste the bugs you want to run from `bugs_list_complete.txt` into `configmap-bugs.yaml`. Make sure the number of bugs in `configmap-bugs.yaml` matches the `completions` and optionally `parallelism` amounts or some pods will fail with “No bug line found…”.

To newly add the configmap to the namespace, run this from deployment/: 

`kubectl create -f configmap-bugs.yaml`

Or if you're just updating it and it already exists, run: 

`kubectl apply -f configmap-bugs.yaml`

## Step 8: Run the job

WAIT! Make sure to double check the job yaml has the following: 
- correct image tag in the field `image`
- values of `completions` matches the number of bugs in the config map

Then, from deployment/ run: 

`kubectl create -f job-repairagent.yaml`

Here are some status checks you can run: 

`kubectl get events --sort-by=.metadata.creationTimestamp`

`kubectl get jobs`

`kubectl describe job repairagent`

`kubectl get pods`

`kubectl logs repairagent-tc42x > logs.txt`

Remember to periodically sample the CPU usage so you can dial it in in the next request:

`kubectl top pod`

After the job has completed, delete it (pods will be deleted by default) to make sure we can mount the PVC helper pod to the PVC: 

`kubectl delete job repairagent`

### Step 9: Move output files from PVC to local directory

Spin up the PVC helper pod again:

`kubectl create -f pod-storage-helper.yaml`

From the experimental_setups folder locally, copy the experiment_1 folder into it with: 

`kubectl cp volume-helper-pod:app/repair_agent/experimental_setups/experiment_1 ./experiment_1`

### Step 10: Clean up resources: 

Delete pod and PVC by running: 

`kubectl delete pod pod-storage-helper`

`kubectl delete pvc repairagent-pvc`


## Optional: Getting files in S3 bucket to Local

S3 —> PVC mounted to helper pod —> Local 

rclone cannot reach S3 endpoint rook-ceph-rgw-nautiluss3.rook (no such host) event when configured. That hostname is cluster-internal, so Nautilus S3 is typically unreachable from local without special network access. Therefore, we need to use an S3 helper pod on the cluster.

1. Spin up S3 helper pod with rclone image and PVC mount point
2. Copy 

To copy folders from PVC mounted to S3 helper pod —> bucket `nautilus:repair-agent-bucket` use this command from the shell of the S3 helper pod: 

`rclone copy /app/repair_agent/experimental_setups/experiment_1 nautilus:repair-agent-bucket --progress --transfers 4 --checkers 8`

Copy from S3 to Local. Run this from my local terminal:

`rclone copy nautilus:repair-agent-bucket ~/Downloads --progress --transfers 4 --checkers 8`

# About S3 rclone step

We use an rclone sidecar to avoid modifying the main repairagent image. The sidecar runs rclone:v1.72-stable, mounts the same PVC at /app/repair_agent/experimental_setups/experiment_1, and computes BUG_DIR from the same indexed job inputs as the main container. It waits for timing.csv to appear, then logs [DONEFILE] running rclone... and syncs that BUG_DIR to nautilus:repair-agent-bucket/. On termination, a preStop hook logs [PRESTOP] running rclone... and syncs to nautilus:repair-agent-bucket/failed/, with terminationGracePeriodSeconds set to allow the final copy to finish.

When the main container exits, Kubernetes starts terminating the pod, and the sidecar gets the termination signal too. It can keep running during the grace period (up to terminationGracePeriodSeconds) before it’s force‑killed. That’s the window your preStop hook and any final rclone sync get to finish.


# About Original Replication 


## Anatomy of User Prompt

```
System prompt: role + 3 states
## Goals → Static
Locate the Bug, Perform code Analysis, Try simple Fixes, Try complex Fixes
## Current state → Dynamic
collect information to understand the bug
collect information to fix the bug
trying out candidate fixes
## Commands → Dynamic
Commands that are available based on the state
## General guidelines → Static
## The format of the fix → Static
description of the json format in which you should write your fixes
### Bug info → Dynamic
Root cause in triggering tests:
The bug is located at exactly these lines numbers: OR FAULT OF OMISSION
The following is the list of buggy methods:
if extract_test_code command is called: ### The code of the failing test cases:
### Test cases results: There are 2 failing test cases, here is the full log of failing cases:
## Hypothesis about the bug:
## Read lines:
## AI generated regeneration of buggy method:
## The list of implementations of some methods in the code base:
extract_method_code
Command extract_method_code returned: We found the following implementations for the method name iterateDomainBounds (we give the body of the method):
## Suggested fixes:
## Executed search queries within the code base:
Lists out the results of search queries from the command search_code_base
## Functions calls extracted based on snippets of code and target files
## DO NOT TRY TO USE THE FOLLOWING COMMANDS IN YOUR NEXT ACTION (NEVER AT ALL)
Guidance on JSON output
You have X commands left.
```

## Anatomy of Model Response
Model_responses_*.txt

The file is written in agent.py inside Agent.parse_and_process_response(...). It is the actual LLM's response which llm_response.content pulls from the OpenAI chat completion API response: response.choices[0].message["content"].

It includes the agent's thoughts and command. 

The reason that it is a JSON blob is that the LLM has been instructed to respond in this format, which has been defined in the user prompt: 

```
Determine exactly one command to use based on the given goals and the progress you have made so far, and respond using the JSON schema specified previously:
Respond strictly with JSON. The JSON should be compatible with the TypeScript type `Response` from the following:
    ```ts
    interface Response {
    // Express your thoughts based on the information that you have collected so far, the possible steps that you could do next and also your reasoning about fixing the bug in question"
    thoughts: string;
    command: {
    name: string;
    args: Record<string, any>;
    };
    }
    ```
```

### Deployment Checklist

**Run Job**
[] kubectl create -f 9-configmap-bugs.yaml
[] kubectl create -f 9-pvc-repairagent.yaml
[] kubectl create -f 9-pod-storage-helper.yaml
[] kubectl describe configmap configmap-bugs-list-9
[] kubectl cp /tmp/tiktoken_cache pod-storage-helper-9:/app/repair_agent/experimental_setups/experiment_1/tiktoken_cache
[] kubectl create -f 9-job-repairagent.yaml
[] kubectl delete pod pod-storage-helper-9

**Extract Logs**
[] kubectl create -f 9-pod-storage-helper.yaml
[] kubectl cp pod-storage-helper-9:/app/repair_agent/experimental_setups/experiment_1/ /Users/kb440/Programming/Research_Repair_Agent/Results/run_9