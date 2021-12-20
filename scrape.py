import argparse
import hashlib
import json
import os
import requests
import yaml

def read_cache(filename):
    cache = {}
    if os.path.isfile(filename):
        with open(filename) as f:
            cache = yaml.safe_load(f)
    else:
        r = requests.get(
            f"{os.environ['CI_API_V4_URL']}/projects/{os.environ['CI_PROJECT_ID']}/jobs/artifacts/{os.environ['CI_COMMIT_REF_NAME']}/raw/{filename}",
            params={"job" : os.environ['CI_BUILD_STAGE'], "job_token" : os.environ['CI_JOB_TOKEN']}
        )
        if r.status_code == 200:
            cache = yaml.safe_load(r.text)

    if not isinstance(cache, dict):
        cache = {}
    cache.setdefault("watches", {})
    print(cache)
    return cache

def write_cache(obj, filename):
    with open(filename, "w") as f:
        yaml.dump(obj, f, default_flow_style=False)

def alert(watch, entry):
    hook = entry.get("hook", watch.get("hook", {}))

    message = f"{entry['url']} changed"
    data = hook.get("payload", json.dumps({"text" : message})).replace("MESSAGE", json.dumps(message))

    if "url" in hook:
        r = requests.request(
            hook.get("method", "POST"),
            hook["url"],
            headers={"content-type" : hook.get("content-type", "application/json")},
            data=data.encode()
        )
    else:
        print(data)

def process(watch, cache):
    for entry in watch.get("watch", []):
        url = entry["url"]
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        value_hash = ''

        r = requests.get(url)
        if r.status_code != entry.get("code", 200):
            # Bail on non matching code
            continue

        data = r.content
        mtype = entry.get("type", "hash")
        if mtype == "hash":
            value_hash = hashlib.sha256(data).hexdigest()

        # If the URL is not previously watched, or the value hash does not match the cache, alert
        if cache["watches"].get(url_hash) != value_hash:
            cache["watches"][url_hash] = value_hash
            alert(watch, entry)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", "-c", type=str, default="cache.yaml")
    parser.add_argument("--input", "-i", type=str, default="watch.yaml")
    args = parser.parse_args()

    cache = read_cache(args.cache)

    with open(args.input) as f:
        watch = yaml.safe_load(f)
    process(watch, cache)
    write_cache(cache, args.cache)
