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


geth-new --datadir ~/snap/geth/common/myDataDir \
     --networkid 1337 \
     --http \
     --http.addr "127.0.0.1" \
     --http.port "8545" \
     --http.api "eth,net,web3,personal,miner,txpool,debug" \
     --allow-insecure-unlock \
     --unlock "0x65e24BBF350cC4665309513d423eA4f6F1CC49f7" \
     --password ~/snap/geth/common/password.txt \
     --miner.gaslimit 60000000 \
     --miner.gasprice 1000000

     ---------------------------------------------------------------------------------------------------------
                                                        New Account
     ---------------------------------------------------------------------------------------------------------
(.venv) merajpi@merajpi:~$ geth --datadir ~/eth-private/data account new
INFO [04-27|07:00:50.484] Maximum peer count                       ETH=50 total=50
INFO [04-27|07:00:50.486] Smartcard socket not found, disabling    err="stat /run/pcscd/pcscd.comm: no such file or directory"
Your new account is locked with a password. Please give a password. Do not forget this password.
Password: 
Repeat password: 

Your new key was generated

Public address of the key:   0x11Db73254c357F47B1194616B0142f738d0f3124
Path of the secret key file: /home/merajpi/eth-private/data/keystore/UTC--2026-04-27T01-01-01.362506119Z--11db73254c357f47b1194616b0142f738d0f3124

- You can share your public address with anyone. Others need it to interact with you.
- You must NEVER share the secret key with anyone! The key controls access to your funds!
- You must BACKUP your key file! Without the key, it's impossible to access account funds!
- You must REMEMBER your password! Without the password, it's impossible to decrypt the key!

--------------------------------------------------------------------------------------------------------

NEW_ADDR="11Db73254c357F47B1194616B0142f738d0f3124"

rm -rf ~/eth-private/data/geth

cat > ~/eth-private/genesis.json << EOF
{
  "config": {
    "chainId": 1337,
    "homesteadBlock": 0,
    "eip150Block": 0,
    "eip155Block": 0,
    "eip158Block": 0,
    "byzantiumBlock": 0,
    "constantinopleBlock": 0,
    "petersburgBlock": 0,
    "istanbulBlock": 0,
    "berlinBlock": 0,
    "londonBlock": 0,
    "clique": { "period": 2, "epoch": 30000 }
  },
  "difficulty": "1",
  "gasLimit": "8000000",
  "extradata": "0x0000000000000000000000000000000000000000000000000000000000000000${NEW_ADDR}0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
  "alloc": {
    "0x${NEW_ADDR}": {
      "balance": "100000000000000000000000"
    }
  }
}
EOF

geth --datadir ~/eth-private/data init ~/eth-private/genesis.json
echo "========== DONE =========="

     ---------------------------------------------------------------------------------------------------------
                                                  Start Geth
     ---------------------------------------------------------------------------------------------------------

NEW_ADDR_WITH_0x="11Db73254c357F47B1194616B0142f738d0f3124"

geth \
  --datadir ~/eth-private/data \
  --networkid 1337 \
  --http \
  --http.addr "127.0.0.1" \
  --http.port 8545 \
  --http.api "eth,net,web3,miner,clique,txpool" \
  --http.corsdomain "*" \
  --http.vhosts "*" \
  --mine \
  --miner.etherbase "$NEW_ADDR_WITH_0x" \
  --unlock "$NEW_ADDR_WITH_0x" \
  --password ~/eth-private/password.txt \
  --allow-insecure-unlock \
  --nodiscover \
  --verbosity 3