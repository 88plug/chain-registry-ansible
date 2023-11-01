import os
import json

def generate_playbook(chain_info):
    if not chain_info.get('pretty_name') or not chain_info.get('daemon_name') or not chain_info.get('chain_id'):
        print(f"Skipping {chain_info.get('chain_name', 'Unknown')} - Required information missing.")
        return None

    if not chain_info.get('peers', {}).get('persistent_peers'):
        print(f"Skipping {chain_info['pretty_name']} - No persistent peers defined.")
        return None

    if not chain_info.get('peers', {}).get('seeds'):
        print(f"Skipping {chain_info['pretty_name']} - No seeds defined.")
        return None


    playbook_content = f'''
---
- name: Setup {chain_info['pretty_name']} Node
  hosts: all
  become: yes

  vars:
    node_moniker: "{chain_info['pretty_name']}"
    seeds: "{','.join(['{}@{}'.format(seed['id'], seed['address']) for seed in chain_info['peers']['seeds']])}"
    peers: "{','.join(['{}@{}'.format(peer['id'], peer['address']) for peer in chain_info['peers']['persistent_peers']])}"

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
        state: present

    # NODE SETUP
    - name: Clone node repository
      git:
        repo: "{chain_info['codebase']['git_repo']}"
        dest: "~/node"
        version: "{chain_info['codebase']['recommended_version']}"
        force: yes

    - name: Install node
      command: make install chdir=~/node

    - name: Copy compiled binaries to /usr/local/bin/
      shell: cp /root/go/bin/* /usr/local/bin/
      args:
        warn: no

    - name: Check if genesis.json exists
      stat:
        path: "/root/.{chain_info['chain_id']}/config/genesis.json"
      register: genesis_stat

    - name: Configure {chain_info['pretty_name']}
      command:
        cmd: "{{ item }}"
        chdir: ~/node
      with_items:
        - "{chain_info['daemon_name']} config chain-id {chain_info['chain_id']}"

    - name: Initialize {chain_info['pretty_name']}
      command:
        cmd: "{chain_info['daemon_name']} init '{{ node_moniker }}' --chain-id {chain_info['chain_id']}"
      when: not genesis_stat.stat.exists

    - name: Download genesis.json
      get_url:
        url: "{chain_info['codebase']['genesis']['genesis_url']}"
        dest: "/root/.{chain_info['chain_id']}/config/genesis.json"

    - name: Update {chain_info['pretty_name']} config with seeds, peers, and other configurations
      lineinfile:
        path: "/root/.{chain_info['chain_id']}/config/config.toml"
        regexp: "{{ item.pattern }}"
        line: "{{ item.line }}"
      with_items:
        - {{ pattern: '^seeds =.*', line: 'seeds = "{{ seeds }}"' }}
        - {{ pattern: '^persistent_peers =.*', line: 'persistent_peers = "{{ peers }}"' }}
        - {{ pattern: '^pruning =.*', line: 'pruning = "custom"' }}
        - {{ pattern: '^pruning-keep-recent =.*', line: 'pruning-keep-recent = "100"' }}
        - {{ pattern: '^pruning-interval =.*', line: 'pruning-interval = "10"' }}
        - {{ pattern: '^minimum-gas-prices =.*', line: 'minimum-gas-prices = "0.001uflix"' }}
        - {{ pattern: '^prometheus =.*', line: 'prometheus = true' }}

    - name: Update {chain_info['pretty_name']} app.toml with pruning and other configurations
      lineinfile:
        path: "/root/.{chain_info['chain_id']}/config/app.toml"
        regexp: "{{ item.pattern }}"
        line: "{{ item.line }}"
      with_items:
        - {{ pattern: '^pruning =.*', line: 'pruning = "custom"' }}
        - {{ pattern: '^pruning-keep-recent =.*', line: 'pruning-keep-recent = "100"' }}
        - {{ pattern: '^pruning-interval =.*', line: 'pruning-interval = "10"' }}
        - {{ pattern: '^minimum-gas-prices =.*', line: 'minimum-gas-prices = "0.001uflix"' }}

    - name: Create {chain_info['pretty_name']} service
      copy:
        dest: "/etc/systemd/system/{{ chain_info['chain_name'] }}.service"
        content: |
          [Unit]
          Description={{ chain_info['pretty_name'] }} Node
          After=network-online.target
          [Service]
          User=root
          ExecStart={{ chain_info['daemon_name'] }} start --x-crisis-skip-assert-invariants
          Restart=on-failure
          RestartSec=10
          [Install]
          WantedBy=multi-user.target
        mode: '0644'


    - name: Reload systemd and start {chain_info['pretty_name']}
      systemd:
        daemon_reload: yes
        enabled: yes
        state: started
        name: {{ chain_info['chain_name'] }}

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
