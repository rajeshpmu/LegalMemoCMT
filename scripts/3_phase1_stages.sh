# Set one clip once, then reuse it for all three models
export SAMPLE_ID=test_dia279_utt9
export VIDEO_PATH=data/MELD/raw/MELD.Raw/test/output_repeated_splits_test/dia279_utt9.mp4
export DEVICE=cuda

# 1) Paper-aligned baseline
DEVICE=$DEVICE \
bash scripts/run_demo_paper_aligned_raw_mp4.sh \
  "$SAMPLE_ID" \
  "$VIDEO_PATH"

# 2) Face-crop gated fusion
DEVICE=$DEVICE \
CHECKPOINT=results/facial_cues/meld_vit_facecrop_gated/fold_4/best_model.pt \
bash scripts/run_phase1_raw_mp4_demo.sh \
  "$SAMPLE_ID" \
  "$VIDEO_PATH"

# 3) Face-crop gated + aux-loss
DEVICE=$DEVICE \
CHECKPOINT=results/facial_cues/meld_vit_facecrop_gated_video_aux/fold_4/best_model.pt \
bash scripts/run_demo_meld_vit_facecrop_gated_video_aux_raw_mp4.sh \
  "$SAMPLE_ID" \
  "$VIDEO_PATH"
