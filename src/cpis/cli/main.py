"""Top-level CLI for the Landsat-first CPI pipeline."""

from __future__ import annotations

import argparse
import sys

from cpis.features.generate_candidates import build_parser as build_features_generate_parser
from cpis.gee.export_year import build_parser as build_gee_export_parser
from cpis.infer.run_year import build_parser as build_infer_run_parser
from cpis.cli.pipeline import build_parser as build_pipeline_run_parser
from cpis.model.train import build_parser as build_model_train_parser
from cpis.postprocess.merge_year import build_parser as build_postprocess_merge_parser
from cpis.qa.labeling import build_parser as build_qa_labeling_parser
from cpis.qa.report_year import build_parser as build_qa_report_parser
from cpis.region.build_arid_ssa import build_parser as build_region_build_parser


def _add_region_group(subparsers) -> None:
    region = subparsers.add_parser("region", help="Region asset commands")
    region_sub = region.add_subparsers(dest="region_cmd")
    build_region_build_parser(region_sub)


def _add_gee_group(subparsers) -> None:
    gee = subparsers.add_parser("gee", help="Google Earth Engine export commands")
    gee_sub = gee.add_subparsers(dest="gee_cmd")
    build_gee_export_parser(gee_sub)


def _add_features_group(subparsers) -> None:
    features = subparsers.add_parser("features", help="Feature/candidate generation commands")
    features_sub = features.add_subparsers(dest="features_cmd")
    build_features_generate_parser(features_sub)


def _add_model_group(subparsers) -> None:
    model = subparsers.add_parser("model", help="Model commands")
    model_sub = model.add_subparsers(dest="model_cmd")
    build_model_train_parser(model_sub)


def _add_infer_group(subparsers) -> None:
    infer = subparsers.add_parser("infer", help="Inference commands")
    infer_sub = infer.add_subparsers(dest="infer_cmd")
    build_infer_run_parser(infer_sub)


def _add_postprocess_group(subparsers) -> None:
    post = subparsers.add_parser("postprocess", help="Postprocess commands")
    post_sub = post.add_subparsers(dest="post_cmd")
    build_postprocess_merge_parser(post_sub)


def _add_qa_group(subparsers) -> None:
    qa = subparsers.add_parser("qa", help="QA/report commands")
    qa_sub = qa.add_subparsers(dest="qa_cmd")
    build_qa_report_parser(qa_sub)
    build_qa_labeling_parser(qa_sub)


def _add_pipeline_group(subparsers) -> None:
    pipeline = subparsers.add_parser("pipeline", help="Orchestration commands")
    pipeline_sub = pipeline.add_subparsers(dest="pipeline_cmd")
    build_pipeline_run_parser(pipeline_sub)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Landsat-first center-pivot detection pipeline for arid SSA")
    sub = p.add_subparsers(dest="group")
    _add_region_group(sub)
    _add_gee_group(sub)
    _add_features_group(sub)
    _add_model_group(sub)
    _add_infer_group(sub)
    _add_postprocess_group(sub)
    _add_qa_group(sub)
    _add_pipeline_group(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 2
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
