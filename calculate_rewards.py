import subprocess
import json
import math
import random
import sys

# Function to run CLI commands and capture the output
def run_command(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, shell=True, check=True)
    return result.stdout.decode('utf-8')

# Set the CLI command based on the argument, default to "memed"
CLI_COMMAND = sys.argv[1] if len(sys.argv) > 1 else "memed"

# Get a list of validators
validators_json = run_command(f"{CLI_COMMAND} query staking validators --output json")
validators_data = json.loads(validators_json)
validators_list = validators_data['validators']

# Select a random validator address
random_validator = random.choice(validators_list)
VALIDATOR_ADDRESS = random_validator['operator_address']

# Get the total annual provisions and total bonded tokens from the blockchain
annual_provisions = float(run_command(f"{CLI_COMMAND} query mint annual-provisions --output json"))
bonded_tokens = float(json.loads(run_command(f"{CLI_COMMAND} query staking pool --output json"))['bonded_tokens'])

# Calculate APR and APY for delegators
delegator_apr = (annual_provisions / bonded_tokens) * 100
delegator_apy = (math.exp(delegator_apr / 100) - 1) * 100

# Get the validator's current rewards rate and calculate APR and APY
validator_rewards_rate = float(json.loads(run_command(f"{CLI_COMMAND} query distribution validator-outstanding-rewards {VALIDATOR_ADDRESS} --output json"))['rewards'][0]['amount'])
validator_apr = (validator_rewards_rate / bonded_tokens) * 100
validator_apy = (math.exp(validator_apr / 100) - 1) * 100

# Print out the APR and APY for both delegators and validators
print(f"Delegator APR: {delegator_apr:.2f}%")
print(f"Delegator APY: {delegator_apy:.2f}%")
print(f"Validator APR: {validator_apr:.2f}%")
print(f"Validator APY: {validator_apy:.2f}%")
