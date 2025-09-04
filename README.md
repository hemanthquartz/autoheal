jobs:
  - name: Installation of MongoDB software
    hosts: "{{ portfolio }}"
    env:
      become: yes
    become_method: runas
    become_user: System
    vars:
      DOMAIN_USERNAME: "{{ DOMAIN_USERNAME }}"
      DOMAIN_PASSWORD: "{{ DOMAIN_PASSWORD }}"
    tasks:
      - name: ensure .NET Framework 4.8 requirement is satisfied for chocolaty CLI v1.4.6+
        block:
          - name: install Chocolately CLI v1.4.6
            win_chocolatey:
              name: 'chocolatey'
              state: latest
              version: '1.4.6'
              force: yes
          - name: install Microsoft .NET Framework 4.8
            win_chocolatey:
              name: 'netfx-4.8'
              state: present
      - name: Check if VM is already domain joined
        win_shell: |
          (Get-WmiObject win32_ComputerSystem).PartOfDomain
        register: domain_check
      - name: Force domain join using PowerShell
        win_domain:
          dns_domain_name: "{{ ansible_facts['hostname'] }}.provider.engineering"
          hostname: "{{ ansible_facts['hostname'] }}"
          user: "{{ DOMAIN_USERNAME }}"
          password: "{{ DOMAIN_PASSWORD }}"
        when: domain_check.stdout.strip() != "True"
      - name: Reboot the host to complete domain join and .NET Framework 4.8 install
        ansible.windows.win_reboot: