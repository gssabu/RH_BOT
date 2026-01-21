import base64
import argparse
from nacl.signing import SigningKey

def main():
    p = argparse.ArgumentParser(description="Generate Ed25519 keypair for the RH bot.")
    p.add_argument("--seed-hex", help="32-byte hex seed for deterministic key (optional).")
    p.add_argument("--env-names", action="store_true",
                   help="Print names matching client.py (.env lines with RH_PUBLIC_KEY_B64 / RH_PRIVATE_KEY_B64).")
    args = p.parse_args()

    if args.seed_hex:
        seed = bytes.fromhex(args.seed_hex)
        if len(seed) != 32:
            raise SystemExit("seed must be 32 bytes (64 hex chars)")
        sk = SigningKey(seed)
    else:
        sk = SigningKey.generate()

    pk = sk.verify_key
    pk_b64 = base64.b64encode(bytes(pk)).decode()
    sk_b64 = base64.b64encode(bytes(sk)).decode()

    if args.env_names:
        # matches client.py expectations; avoids name mismatch accidents
        print(f"RH_PUBLIC_KEY_B64={pk_b64}")
        print(f"RH_PRIVATE_KEY_B64={sk_b64}")
    else:
        # backward compatible names if you prefer
        print("PUBLIC_KEY_BASE64 =", pk_b64)
        print("PRIVATE_KEY_BASE64=", sk_b64)

if __name__ == "__main__":
    main()
