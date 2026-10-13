# Only for the dedicated phucthanh-chatwoot review installation.
require 'json'
require 'securerandom'
result = nil
ActiveRecord::Base.transaction do
  account = Account.find_or_create_by!(name: 'Phuc Thanh Support')
  email = 'admin@phucthanh.local'
  admin = User.find_by(email: email)
  admin_password = nil
  unless admin
    admin_password = SecureRandom.base64(24)
    admin = User.new(name: 'Phuc Thanh Admin', email: email, password: admin_password)
    admin.skip_confirmation!
    admin.save!
  end
  AccountUser.find_or_create_by!(account: account, user: admin) { |membership| membership.role = :administrator }
  bridge = User.find_by(email: 'bridge@phucthanh.local')
  unless bridge
    bridge = User.new(name: 'Phuc Thanh Bridge', email: 'bridge@phucthanh.local', password: SecureRandom.base64(32))
    bridge.skip_confirmation!
    bridge.save!
  end
  AccountUser.find_or_create_by!(account: account, user: bridge) { |membership| membership.role = :agent }
  bot = account.agent_bots.find_or_initialize_by(name: 'Phuc Thanh Gemini')
  bot.assign_attributes(outgoing_url: 'http://hub:8095/webhooks/chatwoot', secret: ENV.fetch('CW_WEBHOOK_SECRET'))
  bot.save!
  inboxes = {}
  [['zalo-personal-1', 'Zalo ca nhan', 'zalo'], ['whatsapp-personal-1', 'WhatsApp ca nhan', 'whatsapp']].each do |key, name, channel|
    inbox = account.inboxes.find_by(name: name)
    unless inbox
      api = Channel::Api.create!(account: account)
      inbox = account.inboxes.create!(name: name, channel: api, enable_auto_assignment: false)
    end
    [admin, bridge].each { |user| InboxMember.find_or_create_by!(inbox: inbox, user: user) }
    assignment = AgentBotInbox.find_or_initialize_by(inbox: inbox)
    assignment.assign_attributes(agent_bot: bot, status: :active)
    assignment.save!
    inboxes[key] = { inbox_id: inbox.id, channel: channel, delivery_enabled: false }
  end
  result = { account: account.id, bot_id: bot.id, token: bridge.access_token.token, inboxes: inboxes,
             admin_email: email, admin_password: admin_password }
end
::Redis::Alfred.delete(::Redis::Alfred::CHATWOOT_INSTALLATION_ONBOARDING)
puts 'PHUCTHANH_BOOTSTRAP=' + JSON.generate(result)

