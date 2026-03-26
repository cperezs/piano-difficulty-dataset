#!/bin/bash
docker run --rm -v "$(cd "$(dirname "$0")" && pwd)":/dataset -w /dataset python:3.12-slim bash create_difficulty_dataset.sh
