import json
from cad_parser.feature_parser import FeatureParser
from cad_parser.primitive_parser import PrimitiveParser
from cad_parser.plane_parser import PlaneParser

def main(input_path="fs/violin.txt", output_path="features.json", report_description=True):
    with open(input_path, "r") as f:
        text = f.read()

    features = {}
    created_plane_ids = []
    feature_ids = []
    primitive_ids = []

    for i, (fid, block) in enumerate(FeatureParser.extract_feature_blocks(text), start=1):
        name = FeatureParser.extract_name(block)
        description = FeatureParser.extract_description(block)
        feature_type, feature_id = FeatureParser.extract_type_and_id(description)
        feature_ids.append((feature_id, feature_type))
        if feature_type == "cPlane":
            created_plane_ids.append(feature_id)

        initial_guess = PrimitiveParser.extract_initial_guess(description, feature_id)
        if feature_type == "newSketch":
            primitives = PrimitiveParser.extract_sketch_primitives(description, initial_guess, primitive_ids)
            feature_data = {
                "name": name,
                "type": feature_type,
                "id": feature_id,
                "primitives": primitives,
            }
        else:
            parameters = PrimitiveParser.extract_parameters(description, feature_type, feature_ids, primitive_ids)
            feature_data = {
                "name": name,
                "type": feature_type,
                "id": feature_id,
                "parameters": parameters,
            }

        if feature_type == "newSketch":
            sketch_plane = PlaneParser.extract_sketch_plane(description, created_plane_ids, feature_ids, primitive_ids)
            feature_data["sketch_plane"] = sketch_plane

        if report_description:
            feature_data["description"] = description

        features[f"feature {i}"] = feature_data

    with open(output_path, "w") as f:
        json.dump(features, f, indent=4)
    
    print("feature_ids:")
    for fid, ftype in feature_ids:
        print(f"  - {fid}: {ftype}")

    print("primitive_ids:")
    for pid, pname in primitive_ids:
        print(f"  - {pid}: {pname}")

    print(f"Saved {len(features)} features with primitives to '{output_path}'")

if __name__ == "__main__":
    # main("fs/00120007.txt", "features.json", report_description=False)
    # all files in fs make json and save in json folder
    import os
    input_dir = "fs_test"
    output_dir = "json_test"
    os.makedirs(output_dir, exist_ok=True)
    for filename in os.listdir(input_dir):
        if filename.endswith(".txt"):
            input_path = os.path.join(input_dir, filename)
            output_path = os.path.join(output_dir, f"{os.path.splitext(filename)[0]}.json")
            print(f"Processing {input_path} -> {output_path}")
            main(input_path, output_path, report_description=False)
    print("All files processed.")
