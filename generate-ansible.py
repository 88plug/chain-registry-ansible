import os
import json

def generate_playbook(chain_info):
    low_gas_price = None  # Initialize the variable to store low gas price
    if not chain_info.get('pretty_name') or not chain_info.get('daemon_name') or not chain_info.get('chain_id'):
        print(f"Skipping {chain_info.get('chain_name', 'Unknown')} - Required information missing.")
        return None

    if not chain_info.get('peers', {}).get('persistent_peers'):
        print(f"Skipping {chain_info['pretty_name']} - No persistent peers defined.")
        return None

    if not chain_info.get('peers', {}).get('seeds'):
        print(f"Skipping {chain_info['pretty_name']} - No seeds defined.")
        return None

    if not chain_info.get('staking', {}).get('staking_tokens'):
        print(f"Skipping {chain_info['pretty_name']} - No staking defined.")
        return None

    # Check if 'fees' and 'fee_tokens' are defined and have at least one entry
    if 'fees' in chain_info and 'fee_tokens' in chain_info['fees'] and chain_info['fees']['fee_tokens']:
        # Iterate over the fee_tokens list
        for token in chain_info['fees']['fee_tokens']:
            # Check if 'low_gas_price' is defined for the token
            if 'low_gas_price' in token:
                low_gas_price = token['low_gas_price']
                print(f"The low gas price for {chain_info['pretty_name']} is {low_gas_price}")
                # Do something with low_gas_price
                break
        else:
            # The else block executes if no break was hit in the for loop,
            # meaning no low_gas_price was found
            print(f"Skipping {chain_info['pretty_name']} - No low gas price defined.")
    else:
        print(f"Skipping {chain_info['pretty_name']} - No fee tokens defined.")


    # Extract node directory from node_home by removing the $HOME/ prefix
    node_home = chain_info.get('node_home')
    if not node_home:
        print(f"Skipping {chain_info.get('chain_name', 'Unknown')} - node_home not provided.")
        return None

    node_dir = node_home.replace('$HOME/', '')

    playbook_content = f'''
---
- name: Setup {chain_info['pretty_name']} Node
  hosts: all
  become: yes

  vars:
    low_gas_price: "token['low_gas_price']"
    node_dir: "{node_dir}"
    seeds: "{','.join(['{}@{}'.format(seed['id'], seed['address']) for seed in chain_info['peers']['seeds']])}"
    peers: "{','.join(['{}@{}'.format(peer['id'], peer['address']) for peer in chain_info['peers']['persistent_peers']])}"
    snapshot_url: "https://polkachu.com/api/v2/chain_snapshots/"

  tasks:
    # SECURITY AND SYSTEM SETUP
    - name: Generate SSH keys
      command:
        cmd: ssh-keygen -t rsa -f ~/.ssh/id_rsa -N ""
        creates: ~/.ssh/id_rsa

    - name: Display public SSH key
      command: cat ~/.ssh/id_rsa.pub
      register: public_key
      changed_when: false
    - debug:
        var: public_key.stdout

    - name: Upgrade system packages
      apt:
        update_cache: yes
        upgrade: yes

    - name: Install necessary packages
      apt:
        name:
          - build-essential
          - git
          - golang
          - fail2ban
          - ufw
          - curl
          - jq
          - lz4
          - bmon
          - iotop
          - htop
          - direnv
          - aria2
        state: present

    # NODE SETUP
    - name: Clone node repository
      git:
        repo: "{chain_info['codebase']['git_repo']}"
        dest: "~/node"
        version: "{chain_info['codebase']['recommended_version']}"
        force: yes

    - name: Download and install libwasmvm.x86_64.so
      become: yes
      block:
        - name: Download libwasmvm.x86_64.so from GitHub
          get_url:
            url: "https://github.com/CosmWasm/wasmvm/releases/download/v1.5.0/libwasmvm.x86_64.so"
            dest: "/usr/local/lib/libwasmvm.x86_64.so"
            mode: '0755'
        - name: Execute ldconfig to refresh shared library cache
          command: ldconfig

    - name: Install node
      command: make build chdir=~/node

    - name: Copy compiled binaries from /root/go/bin to /usr/local/bin/
      shell: cp /root/go/bin/* /usr/local/bin/
      ignore_errors: yes

    - name: Copy compiled binaries from /root/node/bin to /usr/local/bin/
      shell: cp /root/node/bin/* /usr/local/bin/
      ignore_errors: yes

    - name: Copy compiled binaries from /root/node/build to /usr/local/bin/
      shell: cp /root/node/build/* /usr/local/bin/
      ignore_errors: yes

    - name: Check if genesis.json exists
      stat:
        path: "~/{ node_dir }/config/genesis.json"
      register: genesis_stat

    - name: Configure {chain_info['pretty_name']}
      command: "{chain_info['daemon_name']} config chain-id {chain_info['chain_id']}"
      ignore_errors: yes

    - name: Initialize {chain_info['pretty_name']}
      command:
        cmd: "{chain_info['daemon_name']} init {chain_info['chain_name']} --chain-id {chain_info['chain_id']}"
      when: not genesis_stat.stat.exists

    - name: Download genesis.json
      get_url:
        url: "{chain_info['codebase']['genesis']['genesis_url']}"
        dest: "~/{ node_dir }/config/genesis.json"

    - name: Update {chain_info['pretty_name']} config with seeds, peers, and other configurations
      lineinfile:
        path: "~/{ node_dir }/config/config.toml"
        regexp: "{{{{ item.pattern }}}}"
        line: "{{{{ item.line }}}}"
      with_items:
        - {{ pattern: '^seeds =.*', line: 'seeds = "{{{{ seeds }}}}"' }}
        - {{ pattern: '^persistent_peers =.*', line: 'persistent_peers = "{{{{ peers }}}}"' }}
        - {{ pattern: '^pruning =.*', line: 'pruning = "custom"' }}
        - {{ pattern: '^pruning-keep-recent =.*', line: 'pruning-keep-recent = "100"' }}
        - {{ pattern: '^pruning-interval =.*', line: 'pruning-interval = "10"' }}
        - {{ pattern: '^minimum-gas-prices =.*', line: 'minimum-gas-prices = "{ low_gas_price }{ chain_info['staking']['staking_tokens'][0]['denom'] }"' }}
        - {{ pattern: '^prometheus =.*', line: 'prometheus = true' }}

    - name: Update {chain_info['pretty_name']} app.toml with pruning and other configurations
      lineinfile:
        path: "~/{ node_dir }/config/app.toml"
        regexp: "{{{{ item.pattern }}}}"
        line: "{{{{ item.line }}}}"
      with_items:
        - {{ pattern: '^pruning =.*', line: 'pruning = "custom"' }}
        - {{ pattern: '^pruning-keep-recent =.*', line: 'pruning-keep-recent = "100"' }}
        - {{ pattern: '^pruning-interval =.*', line: 'pruning-interval = "10"' }}
        - {{ pattern: '^minimum-gas-prices =.*', line: 'minimum-gas-prices = "{ low_gas_price }{ chain_info['staking']['staking_tokens'][0]['denom'] }"' }}

    - name: Stop systemd {chain_info['pretty_name']}
      systemd:
        state: stopped
        name: { chain_info['chain_name'] }

    - name: Cleanup systemd service
      file:
        path: /etc/systemd/system/{chain_info['chain_name']}.service
        state: absent

    - name: Create {chain_info['pretty_name']} service
      blockinfile:
        path: "/etc/systemd/system/{chain_info['chain_name']}.service"
        block: |
          [Unit]
          Description={chain_info['pretty_name']} Node
          After=network-online.target
          [Service]
          User=root
          ExecStart={chain_info['daemon_name']} start --x-crisis-skip-assert-invariants
          Restart=on-failure
          RestartSec=10
          [Install]
          WantedBy=multi-user.target
        create: yes

    - name: Download and extract the latest snapshot
      shell: |
        set -e  # Exit on error
        SNAP_URL="http://snapshots.autostake.com/{chain_info['chain_id']}/"
        SNAP_NAME=$(curl -s "${{SNAP_URL}}" | egrep -o ">{chain_info['chain_id']}.*.tar.lz4" | tr -d ">" | tail -1)
        if [ -n "${{SNAP_NAME}}" ]; then
          aria2c --out=snapshot.tar.lz4 --check-certificate=false --max-tries=99 --retry-wait=5 --always-resume=true --max-file-not-found=99 --conditional-get=true -s 16 -x 16 -k 1M -j 1 "${{SNAP_URL}}${{SNAP_NAME}}"
          lz4 -c -d snapshot.tar.lz4 | tar -x -C ~/{ node_dir }
          rm -rf snapshot.tar.lz4
        else
          echo "Snapshot name could not be determined."
          exit 1
        fi
      args:
        warn: no
        executable: /bin/bash  # Specify the shell to use
      register: snapshot_result
      changed_when: "'Snapshot name could not be determined.' not in snapshot_result.stdout"

    - name: Reload systemd and start {chain_info['pretty_name']}
      systemd:
        daemon_reload: yes
        enabled: yes
        state: started
        name: { chain_info['chain_name'] }

    - name: Cleanup leftover go directory
      file:
        path: /root/go
        state: absent

    - name: Cleanup leftover node directory
      file:
        path: ~/node
        state: absent
'''
    return playbook_content

base_dir = '.'

# Iterate through each folder in the base directory
for chain_folder in os.listdir(base_dir):
    chain_dir = os.path.join(base_dir, chain_folder)
    if not os.path.isdir(chain_dir) or not os.path.exists(os.path.join(chain_dir, 'chain.json')):
        continue

    if chain_folder == 'testnets' or chain_folder.startswith('.') or chain_folder.startswith('_'):
        continue

    chain_dir = os.path.join(base_dir, chain_folder)
    if os.path.isdir(chain_dir):
        chain_json_path = os.path.join(chain_dir, 'chain.json')
        playbook_path = os.path.join(chain_dir, f'install_{chain_folder}.yml')

        # Load chain.json
        with open(chain_json_path, 'r') as json_file:
            chain_info = json.load(json_file)

            # Add default RPC and P2P ports if not provided
            chain_info['rpc_port'] = chain_info.get('rpc_port', 26657)
            chain_info['p2p_port'] = chain_info.get('p2p_port', 26656)

        # Create Ansible playbook content
        playbook_content = generate_playbook(chain_info)

        if playbook_content is not None:
            # Write playbook content to file
            with open(playbook_path, 'w') as playbook_file:
                playbook_file.write(playbook_content)

            print(f'Generated playbook for {chain_info["pretty_name"]} at {playbook_path}')
