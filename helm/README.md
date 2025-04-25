# Introduction

This helm chart provides a convenient interface for running the Tesla Sync script on a kubernetes cluster, as either a one-shot or scheduled job.

## Add Helm chart (if pushing to a chart repository)
helm repo add tesla-sync <repository-url>

## Install the chart
helm install tesla-sync . \
  --set secrets.teslaloggerDbPassword=your_teslalogger_password \
  --set secrets.teslamateDbPassword=your_teslamate_password \
  --set env.DRYRUN=1

## Re-run the chart once installed
helm upgrade tesla-sync .

## Scheduling Sync Runs
To be addressed in a future update

## View the output of a job run
kubectl logs job/tesla-sync
