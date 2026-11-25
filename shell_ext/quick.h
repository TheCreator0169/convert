// generated, do not edit: written by tools/gen_ext_header.py from convert_win.formats.QUICK and OUTPUTS.
#pragma once
// Same order as the types in tools/gen_ext_header.py (TYPES).
enum QuickType : unsigned char {
    kQuickAudio,
    kQuickVideo,
    kQuickImage,
    kQuickDoc,
    kQuickPdf,
};
static const int kQuickTypeCount = 5;
struct QuickFmt {
    const wchar_t* id;     // --quick argument
    const wchar_t* label;  // shown as 'Convert to <label>'
    const wchar_t* ext;    // output extension without dot
};
static const QuickFmt kQuickAudioFmts[] = {
    {L"mp3", L"MP3", L"mp3"},
    {L"m4a", L"M4A (AAC)", L"m4a"},
    {L"wav", L"WAV", L"wav"},
    {L"flac", L"FLAC", L"flac"},
};
static const size_t kQuickAudioCount = 4;
static const QuickFmt kQuickVideoFmts[] = {
    {L"mp4", L"MP4 (H.264)", L"mp4"},
    {L"webm", L"WebM (VP9)", L"webm"},
    {L"gif", L"Animated GIF", L"gif"},
    {L"mp3", L"MP3", L"mp3"},
};
static const size_t kQuickVideoCount = 4;
static const QuickFmt kQuickImageFmts[] = {
    {L"jpg", L"JPEG", L"jpg"},
    {L"png", L"PNG", L"png"},
    {L"webp", L"WebP", L"webp"},
    {L"pdf", L"PDF", L"pdf"},
};
static const size_t kQuickImageCount = 4;
static const QuickFmt kQuickDocFmts[] = {
    {L"pdf", L"PDF", L"pdf"},
    {L"docx", L"DOCX", L"docx"},
    {L"txt", L"Plain text", L"txt"},
};
static const size_t kQuickDocCount = 3;
static const QuickFmt kQuickPdfFmts[] = {
    {L"png", L"PNG (one per page)", L"png"},
    {L"jpg", L"JPEG (one per page)", L"jpg"},
    {L"txt", L"Plain text", L"txt"},
};
static const size_t kQuickPdfCount = 3;
static const QuickFmt* const kQuickLists[] = {kQuickAudioFmts, kQuickVideoFmts, kQuickImageFmts, kQuickDocFmts, kQuickPdfFmts};
static const size_t kQuickCounts[] = {kQuickAudioCount, kQuickVideoCount, kQuickImageCount, kQuickDocCount, kQuickPdfCount};
