{
  "detectorName": "AWS ALB Target Unhealthy",
  "detectorTags": "aws,elb,alb,targetgroup,health",
  "detectorTeams": "platform-ops",
  "dimensions": "{cloud.provider=aws, cloud.region=us-east-1, service.name=elb, aws.account.id=123456789012, aws.elb.load_balancer=app/prod-alb/50dc6c495c0c9188, aws.elb.load_balancer_arn=arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/prod-alb/50dc6c495c0c9188, aws.elb.target_group=prod-tg, aws.elb.target_group_arn=arn:aws:elasticloadbalancing:us-east-1:123456789012:targetgroup/prod-tg/6d0ecf831eec9f09, aws.elb.target.id=i-0a1b2c3d4e5f67890, aws.elb.target.port=443, aws.elb.availability_zone=us-east-1a, aws.elb.target.health_state=unhealthy, metric=HealthyHostCount}",
  "readableRule": "HealthyHostCount dropped below 1 for the target group (a target is unhealthy).",
  "ruleName": "TG_HealthyHostCount_Below_1",
  "runbookUrl": "https://runbooks.yourcompany.com/aws/alb-target-unhealthy",
  "signalValue": "0",
  "timestamp": "2026-03-01T00:00:00Z",
  "tip": "Check Target Group health check path/port, security groups/NACLs, instance/service status, and recent deployments."
}