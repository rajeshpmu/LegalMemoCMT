from __future__ import annotations

import subprocess
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "implementation_docments" / "LegalMemoCMT_MELD_Face_Crop_ViT_Implementation_Plan.docx"
FIG_DIR = ROOT / "implementation_docments" / "figures" / "meld_vit_facecrop_plan"
FIG_DIR.mkdir(parents=True, exist_ok=True)
PIPELINE_SVG = FIG_DIR / "facecrop_pipeline.svg"
PIPELINE_PNG = FIG_DIR / "facecrop_pipeline.png"


def configure(doc: Document) -> None:
    styles = doc.styles
    styles["Normal"].font.name = "Times New Roman"
    styles["Normal"].font.size = Pt(12)
    for name in ["Title", "Heading 1", "Heading 2", "Heading 3"]:
        if name in styles:
            styles[name].font.name = "Times New Roman"
    section = doc.sections[0]
    section.top_margin = Inches(0.8)
    section.bottom_margin = Inches(0.8)
    section.left_margin = Inches(0.95)
    section.right_margin = Inches(0.95)


def add_para(doc: Document, text: str, *, italic: bool = False, bold: bool = False) -> None:
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)
    r.italic = italic
    r.bold = bold


def add_bullets(doc: Document, items: list[str]) -> None:
    for item in items:
        doc.add_paragraph(item, style="List Bullet")


def add_code(doc: Document, code: str) -> None:
    for line in code.rstrip("\n").split("\n"):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.25)
        r = p.add_run(line)
        r.font.name = "Courier New"
        r.font.size = Pt(9.2)


def add_table(doc: Document, headers: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for cell, header in zip(table.rows[0].cells, headers):
        cell.text = header
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = value


def render_mermaid(code: str, svg_path: Path, png_path: Path) -> None:
    mmd_path = svg_path.with_suffix(".mmd")
    mmd_path.write_text(code, encoding="utf-8")
    subprocess.run(
        ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", str(mmd_path), "-o", str(svg_path), "-b", "white"],
        check=True,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    subprocess.run(
        ["npx", "-y", "@mermaid-js/mermaid-cli", "-i", str(mmd_path), "-o", str(png_path), "-b", "white"],
        check=True,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_doc() -> Document:
    render_mermaid(
        """flowchart LR
  A[Raw MELD MP4 clip] --> B[Sample 16 full RGB frames]
  B --> C[Detect speaker face in each sampled frame]
  C --> D[Crop face region with padding]
  D --> E[Resize crop to 224x224]
  E --> F[Pretrained ViT-Base]
  F --> G[(.npy face embedding)]
  G --> H[Face-crop manifest row]
  H --> I[MELD fold CSVs]
  I --> J[Warm-start training]
  J --> K[Metrics + confusion matrix]
""",
        PIPELINE_SVG,
        PIPELINE_PNG,
    )

    doc = Document()
    configure(doc)

    title = doc.add_paragraph()
    run = title.add_run("LegalMemoCMT MELD Face-Crop ViT Implementation Plan")
    run.bold = True
    run.font.size = Pt(22)
    run.font.name = "Times New Roman"

    subtitle = doc.add_paragraph()
    run = subtitle.add_run(
        "A student-level explanation of why the next facial-cue step should crop the face before ViT, how the new scripts are executed, and what outputs should be expected."
    )
    run.italic = True
    run.font.size = Pt(13)
    run.font.name = "Times New Roman"

    add_para(
        doc,
        "Purpose: this document explains the next facial-cue experiment after the full-frame ViT run. The goal is not to change the model backbone or the MELD fold logic. The only planned change is the visual input path: instead of sending full sampled frames to ViT, the pipeline first crops the face region from each frame and then extracts embeddings from those face crops.",
    )
    add_para(
        doc,
        "Why this matters: the full-frame approach proved that the visual branch works, but it still leans heavily toward neutral predictions. For a courtroom-testimony setting, the face is the more direct source of emotional evidence, so face-crop-before-ViT is the better controlled next ablation.",
    )

    doc.add_heading("1. Why Face Crop Before ViT", level=1)
    add_bullets(
        doc,
        [
            "The face carries the most direct emotion cues: brows, eyes, mouth shape, and tension.",
            "Full frames include background noise, clothing, courtroom objects, and camera framing effects.",
            "Cropping the face makes the ViT input more focused and easier to interpret.",
            "The change is still small enough to be a controlled experiment because the backbone, labels, and folds stay the same.",
        ],
    )
    add_para(
        doc,
        "Student interpretation: the question is not whether video matters. The question is whether ViT should study the whole frame or the speaker face. The face crop path is a better answer for the legal-domain research direction because it emphasizes the human expression instead of the environment around the human.",
    )

    doc.add_heading("2. How This Differs From the Full-Frame Path", level=1)
    add_bullets(
        doc,
        [
            "Full-frame path: sample frames, resize them, send the whole image to ViT.",
            "Face-crop path: sample frames, detect face, crop the face, resize the crop, send only the face region to ViT.",
            "Training path: the same warm-start MELD checkpoint is reused; only the visual features change.",
            "Evaluation path: the same MELD fold splits and the same test analysis scripts are reused.",
        ],
    )
    add_code(
        doc,
        """full frame: clip -> sample frames -> resize -> ViT -> .npy
face crop: clip -> sample frames -> detect face -> crop face -> resize -> ViT -> .npy""",
    )
    add_para(
        doc,
        "The important experimental rule is fairness. If the model gets better or worse after the crop change, that difference should be attributed mainly to the visual input strategy, not to a new loss, a new fold split, or a different checkpoint source.",
    )

    doc.add_heading("3. Script-by-Script Execution Guide", level=1)
    add_table(
        doc,
        ["Script", "What it does", "What it produces"],
        [
            ["scripts/run_meld_vit_facecrop_prepare.sh", "Builds the face-crop manifest and the paper-aligned control MELD CSVs", "data/manifests/meld_vit_facecrop.csv and meld_vit_facecrop_control_cv/"],
            ["scripts/build_meld_vit_facecrop_manifest.py", "Samples frames, crops faces, extracts ViT embeddings, writes .npy files", "data/processed/MELD_VIT_FACECROP/.../*.npy"],
            ["scripts/run_meld_vit_facecrop_video_only_control_fold2.sh", "Runs the dedicated video-only face-crop control for Fold 2", "A video-only control checkpoint and test report for Fold 2"],
            ["scripts/analyze_meld_vit_facecrop_video_only_control_fold2.sh", "Exports video-only control Fold 2 predictions and analysis", "Video-only control confusion matrix and error table"],
            ["scripts/run_meld_vit_facecrop_text_audio_fold2.sh", "Runs the text+audio-only reference on the same face-crop folds", "A non-visual reference checkpoint for Fold 2"],
            ["scripts/analyze_meld_vit_facecrop_text_audio_fold2.sh", "Exports text+audio Fold 2 predictions and analysis", "Text+audio confusion matrix and error table"],
            ["scripts/run_meld_vit_facecrop_fold2.sh", "Runs the full warm-start tri-modal face-crop training for MELD Fold 2", "results/facial_cues/meld_vit_facecrop/fold_2/best_model.pt"],
            ["scripts/analyze_meld_vit_facecrop_fold2.sh", "Exports Fold 2 tri-modal predictions and analysis", "metrics.json, predictions_test.csv, confusion_matrix.csv"],
            ["scripts/run_meld_vit_facecrop_video_only_control_fold4.sh", "Runs the dedicated video-only face-crop control for Fold 4", "A video-only control checkpoint and test report for Fold 4"],
            ["scripts/analyze_meld_vit_facecrop_video_only_control_fold4.sh", "Exports video-only control Fold 4 predictions and analysis", "Video-only control confusion matrix and error table"],
            ["scripts/run_meld_vit_facecrop_text_audio_fold4.sh", "Runs the text+audio-only reference on the same face-crop folds", "A non-visual reference checkpoint for Fold 4"],
            ["scripts/analyze_meld_vit_facecrop_text_audio_fold4.sh", "Exports text+audio Fold 4 predictions and analysis", "Text+audio confusion matrix and error table"],
            ["scripts/run_meld_vit_facecrop_fold4.sh", "Runs the full warm-start tri-modal face-crop training for MELD Fold 4", "results/facial_cues/meld_vit_facecrop/fold_4/best_model.pt"],
            ["scripts/analyze_meld_vit_facecrop_fold4.sh", "Exports Fold 4 tri-modal predictions and analysis", "metrics.json, predictions_test.csv, confusion_matrix.csv"],
            ["scripts/run_meld_vit_facecrop_suite.sh", "Runs the full prepare/train/analyze sequence", "A complete face-crop experiment run"],
            ["scripts/run_meld_vit_facecrop_video_only_control_suite.sh", "Runs the dedicated video-only control sequence", "A standalone video-only control experiment run"],
        ],
    )
    add_para(
        doc,
        "The training engine itself is still the existing warm-start code path. That is deliberate. The model architecture and the paper-aligned checkpoint remain stable so the effect of cropping faces can be isolated cleanly. The fold assignment now uses the paper-aligned MELD split as the reference control, while the visual branch is redirected to the face-crop embeddings.",
    )
    add_para(
        doc,
        "Checkpoint selection is now weighted toward MELD's class imbalance rather than being driven only by accuracy. The new default is weighted F1, with macro F1 reported alongside it so the student can see whether minority emotions really improved.",
    )

    doc.add_heading("4. What the Face-Crop Manifest Builder Does", level=1)
    add_para(
        doc,
        "The manifest builder is the key new script. It starts from the MELD annotation CSV files, finds the raw utterance clip, samples the same 16 frames as the full-frame path, detects the speaker face inside each sampled frame, crops that region, and then sends the face crop to the pretrained ViT model. The ViT output for each frame is saved as a .npy embedding file. The manifest row then points to that file.",
    )
    add_bullets(
        doc,
        [
            "The dataset label column is still the emotion label, not sentiment.",
            "The output feature file is still a .npy array of shape (16, 768).",
            "If no face is detected in a frame, the script falls back to a center crop so the run can continue safely.",
            "The manifest keeps the raw clip path so the source utterance is still traceable.",
        ],
    )
    add_code(
        doc,
        """frames = sample_video_frames(video_path, cfg)
face_frames = [crop_face_frame(frame, cfg, cascade) for frame in frames]
inputs = image_processor(images=list(batch), return_tensors="pt")
outputs = vit_model(**inputs)
hidden = outputs.last_hidden_state[:, 0, :]
np.save(video_feat_path, vit_embeddings)""",
    )
    add_para(
        doc,
        "Student takeaway: the role of face-crop preprocessing is to make the visual signal more focused before ViT sees it. ViT is still the feature extractor. The new script only changes what the feature extractor is looking at.",
    )

    doc.add_heading("5. Why Warm-Start Is Still the Right Training Strategy", level=1)
    add_bullets(
        doc,
        [
            "Start from the best weighted-CE MELD checkpoint so the text-audio backbone is preserved.",
            "Add the face-crop visual branch on top of that baseline.",
            "Keep the same fold splits and pooling choice so the comparison remains fair.",
            "Use the new face-crop embeddings to test whether better visual focus reduces neutral bias.",
        ],
    )
    add_para(
        doc,
        "This is a transfer-learning style experiment. The model is not starting from scratch. It is being extended from a strong text+audio backbone so the effect of the new visual representation can be measured cleanly.",
    )

    doc.add_heading("6. Expected Outputs and How to Read Them", level=1)
    add_bullets(
        doc,
        [
            "The .npy file is the learned visual representation for one utterance after face-crop ViT processing.",
            "The fold CSV files decide which utterances are used for training and validation.",
            "best_model.pt is the best checkpoint by validation accuracy.",
            "metrics.json summarizes accuracy, weighted F1, macro F1, and related scores.",
            "predictions_test.csv shows each utterance's predicted and actual label.",
            "confusion_matrix.csv shows which emotion classes are still being confused.",
        ],
    )
    add_para(
        doc,
        "What to look for: a useful result would reduce the tendency to predict neutral too often and improve minority emotion recall, especially sadness, anger, fear, and disgust. If face crops make the visual branch more focused, the confusion matrix should become less neutral-dominated than the full-frame run.",
    )

    doc.add_heading("6.1 Best Checkpoint Selection and Ablation Order", level=2)
    add_para(
        doc,
        "For this MELD experiment, the checkpoint should not be chosen only by validation accuracy. MELD is imbalanced, so accuracy can hide poor minority-class behavior. The safer default is to select the best checkpoint by weighted F1, and to inspect macro F1 as the class-balance check.",
    )
    add_bullets(
        doc,
        [
            "Weighted F1 is the best default for selecting the checkpoint because it stays sensitive to the overall class distribution.",
            "Macro F1 should be reported alongside it because it reveals whether minority emotions improved.",
            "Accuracy is still useful, but it should not be the only selection rule for an imbalanced MELD experiment.",
        ],
    )
    add_para(
        doc,
        "The next ablation sequence should be read as a small controlled study, not as three unrelated runs. First, run a video-only face-crop branch to see whether the visual signal has independent predictive value. Second, run the text+audio baseline to keep a clean non-visual reference. Third, run the full text+audio+video face-crop model to test whether the visual branch actually adds value on top of the already strong multimodal backbone. The doc should present the runs in that order so the comparison story is easy to explain.",
    )
    add_para(
        doc,
        "Recommended execution order for the current video-signal check: run the face-crop preparation step once, then run the dedicated video-only control Fold 2 and Fold 4 scripts, then analyze those two outputs, and finally run the tri-modal Fold 2 and Fold 4 scripts if you want to compare visual-only and multimodal behavior. The control-suite wrapper can be used only when you want the full video-only control pass in one command.",
    )
    add_table(
        doc,
        ["Run", "Modalities", "Question answered"],
        [
            ["Video-only control face crop", "video", "Does the cropped face stream carry useful emotion signal by itself?"],
            ["Text+audio-only reference", "text,audio", "What is the non-visual reference level for this same manifest/fold setup?"],
            ["Text+audio+video face crop", "text,audio,video", "Does the face-crop branch improve over the text+audio reference?"],
        ],
    )
    add_para(
        doc,
        "If video-only has signal but the full tri-modal model does not improve much, the next technical step should be to make the fusion more selective. In that case, a gated fusion block or a small auxiliary video loss would be more informative than just adding more epochs.",
    )

    doc.add_heading("7. Where This Fits in the Thesis Story", level=1)
    add_para(
        doc,
        "This face-crop branch is the last sensible Phase 1 visual ablation before moving the remaining effort into the courtroom-testimony novelty. It is a clean, scientifically defensible test because it changes only one variable: what part of the frame ViT sees.",
    )
    add_bullets(
        doc,
        [
            "If face crops help, freeze them as the final MELD visual design.",
            "If face crops do not help, keep the full-frame path as the simpler baseline and move on.",
            "Either outcome gives a stronger thesis argument than guessing which visual strategy is best.",
        ],
    )
    add_para(
        doc,
        "Short thesis summary: the project has already shown that full-frame facial cues are technically working but still biased toward neutral. The next controlled step is to ask whether face-crop ViT produces a more discriminative and more courtroom-relevant visual representation.",
    )

    return doc


def main() -> None:
    doc = build_doc()
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
