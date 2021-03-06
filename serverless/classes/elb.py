import os
import boto3
import botocore
import logging

logger = logging.getLogger()

# Global vars: boto3 init
elb_client = boto3.client('elbv2')

class elb_service():
    def create_target_groups(self, client, port, target_name, vpc_id, alb_arn, tags):
        self.client = client
        self.port = port
        self.target_name = target_name
        self.vpc_id = vpc_id
        self.alb_arn = alb_arn
        self.tags = tags

        try:
            targetg = elb_client.create_target_group(
                Name=target_name,
                Port=int(port),
                VpcId=vpc_id,
                Protocol='HTTP',
                HealthCheckPath='/healthcheck',
                HealthCheckPort=port,
                TargetType='ip',
                Tags=tags
            )
            target_arn = targetg['TargetGroups'][0]['TargetGroupArn']
            return target_arn
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'DuplicateTargetGroupName':
                logger.warn(
                    'A target group with the same name ' + client + ' exists, but with different settings')
                targetg = elb_client.describe_target_groups(
                    Names=[client]
                )
                target_arn = targetg['TargetGroups'][0]['TargetGroupArn']
                return target_arn
            else:
                raise error

    def check_for_listener(self, alb_arn):
        self.alb_arn = alb_arn
        is_there_listener = False

        describe_listener_response = elb_client.describe_listeners(
            LoadBalancerArn=alb_arn
        )

        if(len(describe_listener_response['Listeners']) < 1):
            return is_there_listener
        else:
            is_there_listener = True
            return is_there_listener
    
    def create_listener(self, alb_arn, certificate, target_arn, tags):
        self.alb_arn = alb_arn
        self.certificate = certificate
        self.target_arn = target_arn
        self.tags = tags
        
        listener = elb_client.create_listener(
            # LoadBalancerArn=os.environ['lb_arn'],
            LoadBalancerArn=alb_arn,
            Protocol='HTTPS',
            Port=443,
            SslPolicy='ELBSecurityPolicy-2016-08',
            Certificates=[
                {
                    'CertificateArn': certificate,
                },
            ],
            DefaultActions=[
                {
                    'Type': 'forward',
                    'TargetGroupArn': target_arn,
                },
            ],
            Tags=tags
        )
        
        listener_arn = listener['Listeners'][0]['ListenerArn']
        return listener_arn

    def get_listener(self, alb_arn):
        self.alb_arn = alb_arn
        
        describe_listener_response = elb_client.describe_listeners(
            LoadBalancerArn=alb_arn
        )
        
        listener_arn = describe_listener_response['Listeners'][0]['ListenerArn']
        return listener_arn

    def check_for_rules(self, listener_arn):
        self.listener_arn = listener_arn
        number_of_rules = {}

        rules = elb_client.describe_rules(
            # this is gonna have to be dynamic
            ListenerArn=listener_arn,
        )
        
        # there is only one default rule
        if(len(rules['Rules']) < 2):
            number_of_rules['number'] = 0
            number_of_rules['condition'] = False
            return number_of_rules
        # there are multiple rules
        else:
            number_of_rules['number'] = int(rules['Rules'][len(rules['Rules'])-2]['Priority'])+1
            number_of_rules['condition'] = True
            return number_of_rules

    def create_rule(self, listener_arn, target_arn, dns, number_of_rules):
        # int(rules['Rules'][len(rules['Rules'])-2]['Priority'])+1)
        self.listener_arn = listener_arn
        self.target_arn = target_arn
        self.dns = dns
        self.number_of_rules = number_of_rules

        # there are multiple rules
        if(number_of_rules['condition']):
            priority = number_of_rules['number']
        # there is only one default rule
        else:
            priority = 1

        listener_rule = elb_client.create_rule(
            ListenerArn=listener_arn,
            Conditions=[
                {
                    'Field': 'host-header',
                    'Values': [
                        dns
                    ]
                },
            ],
            Priority=priority,
            Actions=[
                {
                    'Type': 'forward',
                    'TargetGroupArn': target_arn,
                    'ForwardConfig': {
                        'TargetGroups': [
                            {
                                'TargetGroupArn': target_arn,
                            },
                        ]
                    }
                },
            ],
        )

        rule_arn = listener_rule['Rules'][0]['RuleArn']
        return rule_arn

    def create_listener_rule(self, alb_arn, certificate, target_arn, tags, dns):
        self.alb_arn = alb_arn
        self.certificate = certificate
        self.target_arn = target_arn
        self.tags = tags
        self.dns = dns

        logger.info("3. Checking to see if there's a Listener")
        is_there_listener = self.check_for_listener(alb_arn)

        listener_arn = ''
        if(is_there_listener):  # if there are listeners, then grab the arn
            listener_arn = self.get_listener(alb_arn)
        else:  # if there are no listeners, then create one
            logger.info("3a. Creating Listener")
            listener_arn = self.create_listener(
                alb_arn, certificate, target_arn, tags)

        # need to get the number of listeners
        # just add one more on top of the latest that
        # the highest priority
        number_of_rules = self.check_for_rules(listener_arn)

        print(number_of_rules)
        logger.info("4. Creating Listener Rule")
        # elb rule
        rule_arn = ''
        if(number_of_rules['condition']):
            rule_arn = self.create_rule(
                listener_arn, target_arn, dns, number_of_rules)
        else:
            rule_arn = self.create_rule(
                listener_arn, target_arn, dns, number_of_rules)

        alb_listener = {}
        alb_listener['listener_arn'] = listener_arn
        alb_listener['rule_arn'] = rule_arn

        return alb_listener

    def delete_listener_rule(self, rule_arn):
        try:
            elb_client.delete_rule(
                RuleArn=rule_arn
            )
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'ValidationError':
                logger.warn('A listener rule ARN must be specified')
            else:
                raise error
    
    def delete_target_group(self, target_arn): 
        try:
            elb_client.delete_target_group(
                TargetGroupArn=target_arn
            )
        except botocore.exceptions.ClientError as error:
            if error.response['Error']['Code'] == 'ValidationError':
                logger.warn('A target group ARN must be specified')
            elif error.response['Error']['Code'] == 'ResourceInUse':
                logger.warn('Target group is currently in used by a listener')
            else:
                raise error
