import sys
import numpy as np

def print_motion_info(path):
    motion = np.load(path)

    for key in motion.files:
        print(f"{key}: {motion[key].shape}")

    print(f"fps_val = {motion['fps'].item()}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python inspect_motion.py <path/to/motion.npz>")
        sys.exit(1)

    motion_path = sys.argv[1]
    
    print_motion_info(motion_path)

if __name__ == '__main__':
    main()
