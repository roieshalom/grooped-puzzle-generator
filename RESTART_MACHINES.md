# Restart Machines in Frankfurt

The machines are still in the old region (iad). To fix:

## Option 1: Destroy and recreate (recommended)

The new deployment should create machines in Frankfurt (fra) automatically, but the old ones need to be removed.

In Fly.io dashboard:
1. Go to your app → Machines
2. Stop/delete the old machines in iad region
3. New deployment will create machines in fra

## Option 2: Check if machines are actually running

The machines might be stopped. Check:
- Machine state (started/stopped)
- Health checks
- Logs

If they're stopped, try starting them manually in the dashboard.

