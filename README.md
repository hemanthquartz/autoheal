# 1️⃣ Install the OpenSSH Server feature
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# 2️⃣ Start and enable the SSH service
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

# (Optional) also start the SSH Agent if you use keys
Set-Service -Name ssh-agent -StartupType Automatic
Start-Service ssh-agent

# 3️⃣ Verify that it's running
Get-Service sshd