#!/bin/bash
# start_workers.sh — run the 3DS-bypass CF workers locally (no Cloudflare needed)
cd "$(dirname "$0")/autohitters"

echo "Starting Stripe 3DS worker on :8787 ..."
node worker_server.mjs stripecheckout.worker.js 8787 &
STRIPE_PID=$!

echo "Starting Whop 3DS worker on :8788 ..."
node worker_server.mjs whop.worker.js 8788 &
WHOP_PID=$!

echo "Workers running. Stripe=$STRIPE_PID Whop=$WHOP_PID"
echo "Ctrl+C to stop."
trap "kill $STRIPE_PID $WHOP_PID 2>/dev/null" EXIT
wait
