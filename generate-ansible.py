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
          - sudo
          - bison
          - golang
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


    - name: Run update-golang.sh with the extracted Go version
      shell: |
        GOVERSION=$(egrep '^go [0-9]+\\.[0-9]+' ~/node/go.mod | egrep -o '[0-9]+\\.[0-9]+')
        echo $GOVERSION > release.txt
        export GOVERSION=$GOVERSION
        curl -s -S -L https://raw.githubusercontent.com/moovweb/gvm/master/binscripts/gvm-installer | bash -
        source ~/.gvm/scripts/gvm && gvm install "go$GOVERSION" && gvm use "go$GOVERSION"
      args:
        executable: /bin/bash

    - name : Compile the node with correct
      shell: source ~/.gvm/scripts/gvm && gvm use "go$GOVERSION" && export GOPATH=~/go && make build
      args:
        executable: /bin/bash
        chdir: ~/node
      environment:
        GOPATH: ~/go

    - name: Locate the compiled daemon binary using Ansible find
      find:
        paths: "/root/node"
        patterns: "{ chain_info['daemon_name'] }"
        recurse: yes
        file_type: file
      register: found_daemon

    - name: Debug the location of the compiled daemon binary
      debug:
        msg: "The compiled daemon binary is located at: {{{{ item.path }}}}"
      loop: "{{{{ found_daemon.files }}}}"
      when: found_daemon.matched > 0

    - name: Copy the compiled daemon binary to /usr/local/bin/ if found
      copy:
        src: "{{{{ item.path }}}}"
        dest: "/usr/local/bin/{ chain_info['daemon_name'] }"
        mode: '0755'
      loop: "{{{{ found_daemon.files }}}}"
      when: found_daemon.matched > 0



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

    - name: Download genesis.json from Cosmos Github
      get_url:
        url: "{chain_info['codebase']['genesis']['genesis_url']}"
        dest: "~/{ node_dir }/config/genesis.json"

    - name: Try to download Address Book from Autostake
      get_url:
        url: "http://snapshots.autostake.com/{chain_info['chain_id']}/addrbook.json"
        dest: "~/{ node_dir }/config/addrbook.json"
      ignore_errors: yes

    - name: Try to download Address Book from Polkachu
      get_url:
        url: "http://snapshots.polkachu.com/addrbook/{chain_info['chain_name']}/addrbook.json"
        dest: "~/{ node_dir }/config/addrbook.json"
      ignore_errors: yes

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
      ignore_errors: yes

    - name: Cleanup systemd service
      file:
        path: /etc/systemd/system/{chain_info['chain_name']}.service
        state: absent
      ignore_errors: yes

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

    - name: Download and extract the latest snapshot from Autostake
      shell: |
        set -e  # Exit on error
        SNAP_URL="http://snapshots.autostake.com/{chain_info['chain_id']}/"
        SNAP_NAME=$(curl -s "${{SNAP_URL}}" | egrep -o ">{chain_info['chain_id']}.*.tar.lz4" | tr -d ">" | tail -1)
        aria2c --out=snapshot.tar.lz4 --check-certificate=false --max-tries=99 --retry-wait=5 --always-resume=true --max-file-not-found=99 --conditional-get=true -s 16 -x 16 -k 1M -j 1 "${{SNAP_URL}}${{SNAP_NAME}}"
        lz4 -c -d snapshot.tar.lz4 | tar -x -C ~/{ node_dir }
        rm -rf snapshot.tar.lz4
      ignore_errors: yes

    - name: Download and extract the latest snapshot from Polkachu
      shell: |
        SNAPSHOTS_DIR_URL="https://snapshots.polkachu.com/snapshots/"
        USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        LATEST=$(curl -s -A "$USER_AGENT" "$SNAPSHOTS_DIR_URL" | grep -oP '{chain_info['chain_name']}.*?\\.lz4' | cut -d'/' -f2)
        SNAPSHOT_URL="https://snapshots.polkachu.com/snapshots/{chain_info['chain_name']}/"
        aria2c --out=snapshot.tar.lz4 --check-certificate=false --max-tries=99 --retry-wait=5 --always-resume=true --max-file-not-found=99 --conditional-get=true -s 16 -x 16 -k 1M -j 1 "${{SNAPSHOT_URL}}${{LATEST}}"
        lz4 -c -d snapshot.tar.lz4 | tar -x -C ~/{ node_dir }
        rm -rf snapshot.tar.lz4
      ignore_errors: yes

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
