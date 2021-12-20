import argparse
import os
import requests
import yaml

def read_cache(filename):
    r = requests.get(
        f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}/jobs/artifacts/{os.environ['CI_COMMIT_REF_NAME']}/raw/{filename}", 
        params={"job" : os.environ['CI_BUILD_STAGE'], "job_token" : os.environ['CI_JOB_TOKEN']}
    )
    print(r.url)
    print(r.status_code)
    print(r.text)
    return r.text

def write_cache(obj, filename):
    with open(args.output, "w") as f:
        yaml.dump(obj, f, default_flow_style=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", "-o", type=str, default="output.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    args = parser.parse_args()

    read_cache(args.output)
    write_cache({"job_id" : os.environ["CI_JOB_ID"]}, args.output)
    
