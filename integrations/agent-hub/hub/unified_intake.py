"""Single intake ownership for new group batches; preserve historical ledgers."""
START_AFTER = 1793415578.6851196
def new_message(message):
 return message.get('timestamp',0)>=START_AFTER

def context_eligible(policy,channel,message):
 from hub.intake_quiet import human_activity
 from hub.order_policy import capture_allowed,allowed
 return (human_activity(message) and capture_allowed(policy,channel,message['thread_id'],message['display_name'])
         and allowed({**policy,channel+'_disable_reply_groups':[]},channel,message['display_name'],'receive_messages')
         and allowed(policy,channel,message['display_name']))
