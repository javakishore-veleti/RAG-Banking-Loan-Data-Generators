#!/usr/bin/env python3
"""Replay DLQ messages back to the main queue (manual / debug).

Usage:
  python3 scripts/enqueue_shards.py --dlq-url <dlq> --queue-url <queue>
Requires: boto3, AWS credentials.
"""
import argparse
import json

import boto3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dlq-url", required=True)
    ap.add_argument("--queue-url", required=True)
    args = ap.parse_args()
    sqs = boto3.client("sqs")
    moved = 0
    while True:
        resp = sqs.receive_message(QueueUrl=args.dlq_url, MaxNumberOfMessages=10,
                                   WaitTimeSeconds=5)
        msgs = resp.get("Messages", [])
        if not msgs:
            break
        for m in msgs:
            sqs.send_message(QueueUrl=args.queue_url, MessageBody=m["Body"])
            sqs.delete_message(QueueUrl=args.dlq_url, ReceiptHandle=m["ReceiptHandle"])
            moved += 1
    print(f"Replayed {moved} shard(s) from DLQ to main queue.")


if __name__ == "__main__":
    main()
