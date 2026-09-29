# AWS setup for this project
#
# Goal: one S3 bucket with raw/ and processed/ prefixes for the Olist lake.

## 1. Create a bucket

1. Sign in to AWS Console → S3 → Create bucket.
2. Choose a **globally unique** name (e.g. `olist-analytics-<yourname>-2026`).
3. Region: pick one and use the same value in `.env` as `AWS_REGION`.
4. Block Public Access: keep **on** (recommended).
5. Create bucket.

## 2. IAM permissions

Use an IAM user or role with at least:

- `s3:ListBucket` on `arn:aws:s3:::YOUR_BUCKET`
- `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on `arn:aws:s3:::YOUR_BUCKET/*`

Minimal policy sketch:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::YOUR_BUCKET"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::YOUR_BUCKET/*"]
    }
  ]
}
```

## 3. Local credentials

```bash
aws configure
# or: aws configure --profile myprofile
```

Then copy `.env.example` → `.env` and set:

```
AWS_REGION=...
S3_BUCKET=YOUR_BUCKET
AWS_PROFILE=          # optional
```

## 4. Verify

```bash
aws s3 ls s3://YOUR_BUCKET/
# or with profile:
aws s3 ls s3://YOUR_BUCKET/ --profile myprofile
```

## 5. Cost note

This project uploads ~tens of MB of CSV/Parquet. Keep the bucket private; delete objects when done if you want to avoid storage charges.
