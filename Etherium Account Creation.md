##### **Geth account creation:**

(.venv) merajpi@merajpi:\~$ geth --datadir \~/snap/geth/common/myDataDir account new

INFO \[04-17|01:49:11.841] Maximum peer count                       ETH=50 LES=0 total=50

INFO \[04-17|01:49:11.841] Smartcard socket not found, disabling    err="stat /run/pcscd/pcscd.comm: no such file or directory"

Your new account is locked with a password. Please give a password. Do not forget this password.

Password:

Repeat password:



Your new key was generated



Public address of the key:   0x65e24BBF350cC4665309513d423eA4f6F1CC49f7

Path of the secret key file: /home/merajpi/snap/geth/common/myDataDir/keystore/UTC--2026-04-16T19-49-19.606390743Z--65e24bbf350cc4665309513d423ea4f6f1cc49f7



\- You can share your public address with anyone. Others need it to interact with you.

\- You must NEVER share the secret key with anyone! The key controls access to your funds!

\- You must BACKUP your key file! Without the key, it's impossible to access account funds!

\- You must REMEMBER your password! Without the password, it's impossible to decrypt the key!



(.venv) merajpi@merajpi:\~$





##### **Start Geth Command**

geth --datadir \~/snap/geth/common/myDataDir --networkid 1337 --mine --miner.threads 1 --miner.etherbase "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7" --unlock "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7" --password \~/snap/geth/common/password.txt --allow-insecure-unlock --rpc --rpcapi "eth,net,web3,personal,miner"

