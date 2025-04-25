# Introduction

This helm chart provides 

# Add Helm chart (if pushing to a chart repository)
helm repo add tesla-sync <repository-url>

# Install the chart
helm install tesla-sync ./helm-chart \
  --set secrets.teslaloggerDbPassword=your_teslalogger_password \
  --set secrets.teslamateDbPassword=your_teslamate_password \
  --set env.DRYRUN=1

## View the output of a job
kubectl logs job/tesla-sync
