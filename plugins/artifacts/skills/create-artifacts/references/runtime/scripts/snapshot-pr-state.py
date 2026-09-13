#!/usr/bin/env python3
"""Capture PR checks/review state plus complete GraphQL review-thread closure."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def run(argv,cwd,allow_404=False):
    result=subprocess.run(argv,cwd=cwd,text=True,capture_output=True,check=False)
    if result.returncode:
        if allow_404 and "404" in result.stderr: return {}
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr",required=True); parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--id",required=True); parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--source-sha",required=True); parser.add_argument("--cwd",type=Path,required=True)
    parser.add_argument("--producer",default="gh"); args=parser.parse_args()
    repo=run(["gh","repo","view","--json","nameWithOwner"],args.cwd)["nameWithOwner"]
    state=run(["gh","pr","view",args.pr,"--repo",repo,"--json","number,url,state,headRefOid,baseRefName,baseRefOid,reviewDecision,statusCheckRollup,latestReviews"],args.cwd)
    state["nameWithOwner"]=repo
    owner,name=repo.split("/",1)
    query='query($owner:String!,$name:String!,$number:Int!,$after:String){repository(owner:$owner,name:$name){pullRequest(number:$number){reviewThreads(first:100,after:$after){pageInfo{hasNextPage endCursor}nodes{id isResolved}}}}}'
    nodes=[]; cursor=None
    while True:
        argv=["gh","api","graphql","-f","query="+query,"-F","owner="+owner,"-F","name="+name,"-F","number="+str(state["number"])]
        if cursor: argv += ["-F","after="+cursor]
        connection=run(argv,args.cwd)["data"]["repository"]["pullRequest"]["reviewThreads"]
        nodes.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]: break
        cursor=connection["pageInfo"]["endCursor"]
    state["reviewThreadCount"]=len(nodes); state["unresolvedReviewThreadIds"]=[node["id"] for node in nodes if not node["isResolved"]]
    state["reviewThreadsComplete"]=not state["unresolvedReviewThreadIds"]
    protection=run(["gh","api",f"repos/{repo}/branches/{state['baseRefName']}/protection"],args.cwd,allow_404=True)
    contexts=protection.get("required_status_checks") or {}
    required_checks=contexts.get("contexts",[])+[item.get("context") for item in contexts.get("checks",[]) if item.get("context")]
    reviews=protection.get("required_pull_request_reviews") or {}
    rulesets=run(["gh","api",f"repos/{repo}/rules/branches/{state['baseRefName']}"],args.cwd)
    unknown=[]
    for rule in rulesets:
        kind=rule.get("type"); params=rule.get("parameters") or {}
        if kind=="required_status_checks":
            required_checks += [item.get("context") for item in params.get("required_status_checks",[]) if item.get("context")]
        elif kind=="pull_request":
            reviews["required_approving_review_count"]=max(int(reviews.get("required_approving_review_count",0)),int(params.get("required_approving_review_count",0)))
        elif kind in {"deletion","non_fast_forward","creation","update","required_linear_history"}:
            pass
        else: unknown.append(kind)
    if unknown: raise RuntimeError("uninterpreted effective merge rules: "+", ".join(sorted(set(unknown))))
    state["requiredPolicy"]={"source":"GitHub branch protection and effective rules APIs",
        "ruleIds":[rule.get("ruleset_id") or rule.get("id") for rule in rulesets],
        "requiredChecks":sorted(set(required_checks)),"requiredApprovals":int(reviews.get("required_approving_review_count",0))}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as handle:
        json.dump(state,handle,indent=2); handle.write("\n")
    command=[sys.executable,str(Path(__file__).with_name("record-pr-evidence.py")),"--manifest",str(args.manifest),"--id",args.id,"--kind","pr-state","--file",str(args.output),"--producer",args.producer,"--command","gh pr view + GitHub GraphQL reviewThreads","--source-sha",args.source_sha,"--applies-to","head","--cwd",str(args.cwd),"--state","PASS"]
    result=subprocess.run(command,check=False)
    if result.returncode: args.output.unlink(missing_ok=True)
    return result.returncode
if __name__=="__main__": raise SystemExit(main())
