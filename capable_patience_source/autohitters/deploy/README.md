# Deploy 3DS-bypass workers to Cloudflare

Two folders:

  deploy/stripe/   -> stripecheckout.worker.js  (Stripe 3DS bypass)
  deploy/whop/     -> whop.worker.js            (Whop 3DS bypass)

## Deploy each worker

    cd deploy/stripe
    npm install            # installs wrangler
    npx wrangler login     # opens browser, log into your CF account
    npx wrangler deploy    # deploys

    cd ../whop
    npm install
    npx wrangler deploy

After deploy, wrangler prints the URL, e.g.:

    https://stripe-3ds-bypass.<your-account>.workers.dev
    https://whop-3ds-bypass.<your-account>.workers.dev

## Point the bot at the deployed workers

Set these env vars before starting the bot:

    export STRIPE_3DS_WORKER=https://stripe-3ds-bypass.<your-account>.workers.dev
    export WHOP_3DS_WORKER=https://whop-3ds-bypass.<your-account>.workers.dev

(The bot already reads STRIPE_3DS_WORKER / WHOP_3DS_WORKER from env,
defaulting to localhost:8787 / 8788 for local dev.)

## Local dev (no CF needed)

    cd ..   # back to autohitters/
    node worker_server.mjs stripecheckout.worker.js 8787
    node worker_server.mjs whop.worker.js 8788
