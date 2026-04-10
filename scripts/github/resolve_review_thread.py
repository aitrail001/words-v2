#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo_name(explicit_repo: str | None) -> str:
    if explicit_repo:
        return explicit_repo
    return _run_gh(["repo", "view", "--json", "nameWithOwner", "--template", "{{.nameWithOwner}}"])


def _comment_node_id(repo: str, comment_id: int) -> str:
    payload = json.loads(_run_gh(["api", f"repos/{repo}/pulls/comments/{comment_id}"]))
    node_id = payload.get("node_id")
    if not node_id:
        raise RuntimeError(f"Review comment {comment_id} did not include a node_id")
    return str(node_id)


def _thread_id_for_comment(repo: str, pr_number: int, comment_id: int) -> str:
    owner, name = repo.split("/", 1)
    query = """
    query($owner: String!, $name: String!, $pr: Int!, $after: String) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100, after: $after) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              isResolved
              comments(first: 100) {
                pageInfo {
                  hasNextPage
                  endCursor
                }
                nodes {
                  databaseId
                }
              }
            }
          }
        }
      }
    }
    """
    after: str | None = None
    while True:
        args = [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"pr={pr_number}",
        ]
        if after:
            args.extend(["-F", f"after={after}"])
        payload = json.loads(_run_gh(args))
        threads = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
        for thread in threads["nodes"]:
            for comment in thread["comments"]["nodes"]:
                if int(comment["databaseId"]) == comment_id:
                    return str(thread["id"])
            comment_page = thread["comments"].get("pageInfo", {})
            comment_after = comment_page.get("endCursor")
            while comment_page.get("hasNextPage"):
                comments_query = """
                query($owner: String!, $name: String!, $pr: Int!, $threadId: ID!, $after: String) {
                  repository(owner: $owner, name: $name) {
                    pullRequest(number: $pr) {
                      id
                    }
                  }
                  node(id: $threadId) {
                    ... on PullRequestReviewThread {
                      comments(first: 100, after: $after) {
                        pageInfo {
                          hasNextPage
                          endCursor
                        }
                        nodes {
                          databaseId
                        }
                      }
                    }
                  }
                }
                """
                comments_payload = json.loads(
                    _run_gh(
                        [
                            "api",
                            "graphql",
                            "-f",
                            f"query={comments_query}",
                            "-F",
                            f"owner={owner}",
                            "-F",
                            f"name={name}",
                            "-F",
                            f"pr={pr_number}",
                            "-F",
                            f"threadId={thread['id']}",
                            "-F",
                            f"after={comment_after}",
                        ]
                    )
                )
                comments = comments_payload["data"]["node"]["comments"]
                for comment in comments["nodes"]:
                    if int(comment["databaseId"]) == comment_id:
                        return str(thread["id"])
                comment_page = comments["pageInfo"]
                comment_after = comment_page.get("endCursor")
        if not threads["pageInfo"]["hasNextPage"]:
            break
        after = str(threads["pageInfo"]["endCursor"])
    raise RuntimeError(f"Could not find review thread for comment {comment_id} on PR #{pr_number}")


def _reply_to_comment(repo: str, pr_number: int, comment_id: int, body: str) -> None:
    _run_gh(
        [
            "api",
            f"repos/{repo}/pulls/{pr_number}/comments/{comment_id}/replies",
            "--method",
            "POST",
            "-f",
            f"body={body}",
        ]
    )


def _resolve_thread(thread_id: str) -> None:
    mutation = """
    mutation($threadId: ID!) {
      resolveReviewThread(input: {threadId: $threadId}) {
        thread {
          id
          isResolved
        }
      }
    }
    """
    _run_gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={mutation}",
            "-F",
            f"threadId={thread_id}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reply to a PR review comment and resolve its review thread.",
    )
    parser.add_argument("--pr", type=int, required=True, help="pull request number")
    parser.add_argument("--comment-id", type=int, required=True, help="numeric PR review comment id")
    parser.add_argument("--repo", help="repository in owner/name form; defaults to current gh repo")
    parser.add_argument("--body", help="reply body to post before resolving the thread")
    parser.add_argument("--body-file", type=Path, help="path to a reply body file")
    parser.add_argument("--resolve-only", action="store_true", help="resolve the thread without posting a reply")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.resolve_only and (args.body or args.body_file):
        parser.error("--resolve-only cannot be combined with --body or --body-file")
    if not args.resolve_only and not args.body and not args.body_file:
        parser.error("provide --body, --body-file, or --resolve-only")

    repo = _repo_name(args.repo)
    thread_id = _thread_id_for_comment(repo, args.pr, args.comment_id)

    if not args.resolve_only:
        body = args.body_file.read_text(encoding="utf-8") if args.body_file else str(args.body)
        _reply_to_comment(repo, args.pr, args.comment_id, body)

    _resolve_thread(thread_id)

    print(
        json.dumps(
            {
                "repo": repo,
                "pr": args.pr,
                "comment_id": args.comment_id,
                "thread_id": thread_id,
                "replied": not args.resolve_only,
                "resolved": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
