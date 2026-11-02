#!/usr/bin/env bash
# Query Loom's public API for one video. Prints the raw JSON response to stdout.
#
# Usage: loom-api.sh <meta|transcript|chapters|video-url|raw-video-url> <video-id> [password]
#
# Endpoints and payloads mirror yt-dlp's Loom extractor (yt_dlp/extractor/loom.py),
# the maintained source of truth for this unofficial API.
set -euo pipefail

ACTION="${1:?usage: loom-api.sh <meta|transcript|chapters|video-url|raw-video-url> <video-id> [password]}"
VIDEO_ID="${2:?missing video id (32 hex chars from the loom.com/share/<id> URL)}"
PASSWORD="${3:-}"

if [ -n "$PASSWORD" ]; then
  PASSWORD_JSON="\"$PASSWORD\""
else
  PASSWORD_JSON="null"
fi

graphql() {
  local operation="$1" query="$2" extra_vars="${3:-}"
  curl -sS https://www.loom.com/graphql \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json' \
    -H 'Origin: https://www.loom.com' \
    -H 'x-loom-request-source: loom_web_45a5bd4' \
    -H 'apollographql-client-name: web' \
    -H 'apollographql-client-version: 45a5bd4' \
    -d "{\"operationName\":\"$operation\",\"variables\":{\"videoId\":\"$VIDEO_ID\",\"password\":$PASSWORD_JSON$extra_vars},\"query\":\"$query\"}"
}

rest_url_endpoint() {
  local endpoint="$1"
  # anonID just has to look like a UUID; /dev/urandom exists on linux, macOS and git-bash.
  local hex anon
  hex=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
  anon="${hex:0:8}-${hex:8:4}-${hex:12:4}-${hex:16:4}-${hex:20:12}"
  curl -sS "https://www.loom.com/api/campaigns/sessions/$VIDEO_ID/$endpoint" \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json' \
    -d "{\"anonID\":\"$anon\",\"deviceID\":null,\"force_original\":false,\"password\":$PASSWORD_JSON}"
}

case "$ACTION" in
  meta)
    graphql GetVideoSSR 'query GetVideoSSR($videoId: ID!, $password: String) { getVideo(id: $videoId, password: $password) { __typename ... on RegularUserVideo { id name description createdAt owner { display_name } video_properties { duration durationMs width height } } ... on VideoPasswordMissingOrIncorrect { message } ... on PrivateVideo { status message } } }'
    ;;
  transcript)
    graphql FetchVideoTranscript 'query FetchVideoTranscript($videoId: ID!, $password: String) { fetchVideoTranscript(videoId: $videoId, password: $password) { ... on VideoTranscriptDetails { id video_id source_url captions_source_url } ... on GenericError { message } } }'
    ;;
  chapters)
    graphql FetchChapters 'query FetchChapters($videoId: ID!, $password: String) { fetchVideoChapters(videoId: $videoId, password: $password) { ... on VideoChapters { video_id content } ... on EmptyChaptersPayload { content } ... on InvalidRequestWarning { message } ... on Error { message } } }'
    ;;
  video-url)
    rest_url_endpoint transcoded-url
    ;;
  raw-video-url)
    rest_url_endpoint raw-url
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    exit 2
    ;;
esac
