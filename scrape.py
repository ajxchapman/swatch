import argparse
import os
import requests

def get_cache():
    r = requests.get(
        f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}/jobs/artifacts/{os.environ['CI_COMMIT_REF_NAME']}/raw/cache.yaml", 
        params={"job" : os.environ['CI_BUILD_STAGE'] : "job_token" : os.environ['CI_JOB_TOKEN']}
    )
    print(r.status_code)
    print(r.body)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", type=str, default="output.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    args = parser.parse_args()
    get_cache()
    with open(parser.output, "w") as f:
        print(os.environ["CI_JOB_ID"])
        f.write(os.environ["CI_JOB_ID"])
