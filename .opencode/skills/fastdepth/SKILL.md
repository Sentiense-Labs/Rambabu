---
name: fastdepth
description: FastDepth monocular depth estimation guide for embedded systems. Covers model architecture (MobileNet encoder + NNConv5 decoder), ONNX/TVM deployment, Pi-compatible inference, input preprocessing, and integration with camera pipelines. Use this skill when adding depth perception to the RC car.
---

# FastDepth — Monocular Depth Estimation

FastDepth (ICRA 2019) produces dense depth maps from single RGB images at real-time speeds on embedded hardware. Architecture: MobileNet-v1 encoder + NNConv5 decoder with depthwise separable convolutions and additive skip connections.

**Paper**: "FastDepth: Fast Monocular Depth Estimation on Embedded Systems" (Wofk et al., ICRA 2019)
**Repo**: https://github.com/dwofk/fast-depth
**License**: MIT

## Why FastDepth for this car

- Single RGB camera → dense depth map (no stereo, no LiDAR, no depth sensor needed)
- Designed for embedded: 0.37 GMACs, runs at ~27 FPS on Jetson TX2 GPU
- Supplements the HC-SR04 ultrasonic (which only gives one distance point straight ahead)
- Enables obstacle width/height estimation, gap detection, and spatial reasoning the brain currently cannot do

## Model Variants

| Model | Description | Recommended |
|-------|-------------|-------------|
| `mobilenet-nnconv5dw-skipadd-pruned` | Pruned, skip connections, depthwise decoder | Yes |
| `mobilenet-nnconv5dw-skipadd` | Same without pruning | If accuracy > speed |
| `mobilenet-nnconv5dw` | No skip connections | No |
| `mobilenet-nnconv5` | Standard convolutions in decoder | No |

Always use the pruned variant for Pi deployment.

## Installation & Setup

### Dependencies (on development machine)

```bash
uv add torch torchvision
uv add opencv-python numpy h5py matplotlib imageio scikit-image
```

### Get the pretrained model

```bash
mkdir -p models/fastdepth
# Download the pruned model
wget -P models/fastdepth/ \
  http://datasets.lids.mit.edu/fastdepth/results/mobilenet-nnconv5dw-skipadd-pruned/
```

### Model definition

The model is defined in `models.py` from the FastDepth repo. Key structure:

```python
import torch
import torch.nn as nn

# The model expects:
#   Input:  RGB image tensor, shape (B, 3, 224, 224), normalized ImageNet-style
#   Output: Depth map tensor, shape (B, 1, 224, 224), values in meters
```

## Input Preprocessing

Critical — get this wrong and predictions are garbage:

```python
import cv2
import numpy as np
import torch
from torchvision import transforms

# Standard ImageNet normalization (FastDepth was trained on NYU Depth V2 with these)
transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225]
    ),
])

def preprocess_frame(frame_bgr: np.ndarray) -> torch.Tensor:
    """Preprocess a BGR frame from Pi Camera for FastDepth.

    Args:
        frame_bgr: OpenCV BGR image (any resolution).

    Returns:
        Tensor of shape (1, 3, 224, 224), normalized.
    """
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    tensor = transform(frame_rgb)
    return tensor.unsqueeze(0)  # add batch dimension
```

## Inference

### PyTorch (development machine with CUDA)

```python
import torch

model = torch.load("models/fastdepth/model.pth", map_location="cpu")
model.eval()

with torch.no_grad():
    input_tensor = preprocess_frame(frame)
    depth = model(input_tensor)  # shape: (1, 1, 224, 224)
    depth_map = depth.squeeze().numpy()  # shape: (224, 224), values in meters
```

### ONNX Export (for Pi deployment)

```python
import torch

model = torch.load("models/fastdepth/model.pth", map_location="cpu")
model.eval()

dummy_input = torch.randn(1, 3, 224, 224)
torch.onnx.export(
    model,
    dummy_input,
    "models/fastdepth/fastdepth.onnx",
    input_names=["input"],
    output_names=["depth"],
    opset_version=11,
)
```

### ONNX Runtime on Raspberry Pi 5

```bash
# On the Pi
pip install onnxruntime  # CPU-only is fine for Pi 5
```

```python
import onnxruntime as ort
import numpy as np

session = ort.InferenceSession("models/fastdepth/fastdepth.onnx")

def predict_depth(frame_bgr: np.ndarray) -> np.ndarray:
    """Run FastDepth inference via ONNX Runtime.

    Returns:
        Depth map as numpy array, shape (224, 224), values in meters.
    """
    input_tensor = preprocess_frame(frame_bgr).numpy()
    outputs = session.run(None, {"input": input_tensor})
    return outputs[0].squeeze()  # (224, 224)
```

### TVM Compilation (maximum Pi performance)

FastDepth repo includes TVM auto-tuning configs for Jetson TX2. For Pi 5:
1. Export to ONNX first
2. Use TVM to compile for `llvm -device=arm_cpu -mtriple=aarch64-linux-gnu`
3. Auto-tune on the Pi for best results

See: https://github.com/dwofk/fast-depth/tree/master/tvm_compile

## Interpreting Depth Maps

```python
import numpy as np

def analyze_depth(depth_map: np.ndarray) -> dict:
    """Extract obstacle information from a depth map.

    Args:
        depth_map: (224, 224) array, values in meters.

    Returns:
        Dict with min/max/mean depth, obstacle zones.
    """
    # Divide into left/center/right thirds
    h, w = depth_map.shape
    third = w // 3

    left = depth_map[:, :third]
    center = depth_map[:, third:2*third]
    right = depth_map[:, 2*third:]

    return {
        "min_depth_m": float(np.min(depth_map)),
        "max_depth_m": float(np.max(depth_map)),
        "mean_depth_m": float(np.mean(depth_map)),
        "left_mean_m": float(np.mean(left)),
        "center_mean_m": float(np.mean(center)),
        "right_mean_m": float(np.mean(right)),
        "closest_zone": ["left", "center", "right"][
            np.argmin([np.min(left), np.min(center), np.min(right)])
        ],
    }
```

## Integration with this RC Car

### As a lib/ module

Create `lib/depth.py` following the project conventions:
- One class: `DepthEstimator`
- Methods return dicts (LLM-callable)
- No cross-imports within `lib/`
- Read any config from `config/__init__.py`

```python
# lib/depth.py — skeleton
class DepthEstimator:
    """FastDepth monocular depth estimation from Pi Camera frames."""

    def __init__(self, model_path: str, camera):
        # Load ONNX model, store camera reference
        pass

    def get_depth_map(self) -> dict:
        """Capture frame and return depth analysis.

        Returns:
            {"min_depth_m": float, "center_mean_m": float, ...}
        """
        pass

    def get_obstacle_width(self, threshold_m: float = 0.5) -> dict:
        """Estimate obstacle width at a distance threshold.

        Returns:
            {"obstacle_detected": bool, "width_fraction": float, "gap_left": bool, "gap_right": bool}
        """
        pass
```

### As a brain tool

Register in `brain/tools.py` alongside existing tools:
```python
def execute_depth_scan(hardware_ctx) -> dict:
    """Get depth map analysis from camera."""
    return hardware_ctx.depth.get_depth_map()
```

### Performance expectations on Pi 5

| Runtime | FPS estimate | Notes |
|---------|-------------|-------|
| PyTorch CPU | ~2-3 FPS | Usable but slow |
| ONNX Runtime CPU | ~5-8 FPS | Recommended starting point |
| TVM optimized | ~10-15 FPS | Requires auto-tuning on Pi |

The camera already runs at 30 FPS — depth inference will be the bottleneck. Run depth on a separate thread with cached results (same pattern as `lib/ultrasonic.py`).

## Dataset

FastDepth was trained on NYU Depth V2 (indoor scenes, 0.5-10m range). This matches the car's typical operating environment well. Outdoor performance will be less accurate.

## Reference

- GitHub: https://github.com/dwofk/fast-depth
- Paper: http://fastdepth.mit.edu/
- Pre-trained models: http://datasets.lids.mit.edu/fastdepth/results/
- NYU Depth V2 dataset: http://datasets.lids.mit.edu/fastdepth/data/nyudepthv2.tar.gz
