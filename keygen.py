from nacl.signing import SigningKey
import base64

if __name__ == "__main__":
    sk = SigningKey.generate()         # Ed25519 private
    pk = sk.verify_key                 # public
    print("PUBLIC_KEY_BASE64 =", base64.b64encode(bytes(pk)).decode())
    print("PRIVATE_KEY_BASE64=", base64.b64encode(bytes(sk)).decode())
