import json
import torch
import os
from .build_dataset import build_mmdet_dataset
from .build_model import build_mmdet_model
from tools.utils import stdout_off, stdout_on


def detect_dataset(model, dataset, out_file):
    print("Detection.")

    # 1) build model (or accept pre-built)
    print("1.build model.", end=' ')
    stdout_off()
    if isinstance(model, dict):
        model = build_mmdet_model(model)
    else:
        print('skip.')
    stdout_on()
    print("done.")

    # Force CPU
    device = torch.device("cpu")
    model.to(device)
    model.eval()

    # 2) build data loader
    print("2.build data loader.", end=" ")
    stdout_off()
    data_loader = build_mmdet_dataset(**dataset)

    # model may be wrapped in .module in other paths, but on CPU we keep it plain
    if getattr(model, "CLASSES", None) is None:
        model.CLASSES = data_loader.dataset.CLASSES
    stdout_on()
    print("done.")

    # 3) detect (CPU)
    print("3.detect.")
    stdout_off()
    outputs = []
    model.eval()

    def _unwrap_dc(x):
        # unwrap DataContainer repeatedly
        while x is not None and x.__class__.__name__ == "DataContainer":
            x = x.data
        return x

    def _deep_unwrap(x):
        x = _unwrap_dc(x)
        if isinstance(x, dict):
            return {k: _deep_unwrap(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [ _deep_unwrap(v) for v in x ]
        return x

    outputs = []
    model.eval()

    for data in data_loader:
        # 1) fully unwrap the entire batch (removes all DataContainers)
        data = _deep_unwrap(data)

        # 2) FORCE img_metas into List[Dict]
        if "img_metas" in data:
            im = _deep_unwrap(data["img_metas"])

            # If it's a dict keyed by ints/strings, convert to sorted list of values
            if isinstance(im, dict):
                # Try to sort keys if possible
                try:
                    keys = sorted(im.keys(), key=lambda k: int(k) if str(k).isdigit() else str(k))
                    im = [im[k] for k in keys]
                except Exception:
                    # fallback: just use values
                    im = list(im.values())

            # unwrap one more time in case im[0] was itself nested
            im = _deep_unwrap(im)

            # squash [[...]] -> [...]
            while isinstance(im, list) and len(im) == 1 and isinstance(im[0], list):
                im = im[0]

            # if we got a single dict, wrap it
            if isinstance(im, dict):
                im = [im]

            # final validation: must be list of dicts
            if not (isinstance(im, list) and len(im) > 0 and isinstance(im[0], dict)):
                raise TypeError(f"img_metas wrong type/shape: {type(im)} sample={str(im)[:200]}")

            data["img_metas"] = im


        # 3) unwrap img similarly (remove nesting)
        if "img" in data:
            img = data["img"]
            img = _deep_unwrap(img)

            # common shapes: [[tensor]] or [tensor]
            while isinstance(img, list) and len(img) == 1 and isinstance(img[0], list):
                img = img[0]

            data["img"] = img

        # 4) DEBUG for first batch only (optional but useful)
        if len(outputs) == 0:
            print("DEBUG img_metas:", type(data.get("img_metas")), "len", len(data.get("img_metas", [])))
            if "img_metas" in data:
                print("DEBUG img_metas[0] type:", type(data["img_metas"][0]))
            print("DEBUG img type:", type(data.get("img")))

        # 5) FINAL img_metas check and debug
        if "img_metas" in data:
            im = data["img_metas"]
            print("FINAL img_metas type:", type(im), "len:", len(im))
            if isinstance(im, dict):
                print("WARNING: img_metas is dict, converting to list of values.")
                data["img_metas"] = list(im.values())
            elif not (isinstance(im, list) and len(im) > 0 and isinstance(im[0], dict)):
                print("WARNING: img_metas is not a list of dicts, wrapping.")
                data["img_metas"] = [im] if isinstance(im, dict) else list(im)
            print("FINAL img_metas sample:", str(data["img_metas"])[:200])

        # 5) run model
        with torch.no_grad():
            result = model(return_loss=False, rescale=True, **data)

        outputs.append(result)


    stdout_on()
    print("done.")

    # 4) save result
    print("4.save result.", end=' ')
    os.makedirs(os.path.split(out_file)[0], mode=0o777, exist_ok=True)

    if not outputs:
        js_data = []
    elif isinstance(outputs[0], list):
        js_data = data_loader.dataset._det2json(outputs)
    elif isinstance(outputs[0], tuple):
        js_data = data_loader.dataset._segm2json(outputs)[1]
    else:
        js_data = []

    with open(out_file, "w") as f:
        json.dump(js_data, f, indent=4)
    print("done.")
