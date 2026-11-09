"""Apply the Africa's Talking SMS Settings configuration to existing sites."""

from crm.patches.v1_0.seed_africas_talking_sms_settings import execute as configure


def execute():
	"""Run the authoritative SMS Settings configuration once during migration."""
	configure()
