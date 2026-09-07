import 'dart:io';
import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:archive/archive.dart';
import 'package:path_provider/path_provider.dart';
import '../models/batch_model.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

class ReviewScreen extends StatefulWidget {
  final BatchResponse batchResponse;
  final ApiService apiService;

  const ReviewScreen({
    super.key,
    required this.batchResponse,
    required this.apiService,
  });

  @override
  State<ReviewScreen> createState() => _ReviewScreenState();
}

class _ReviewScreenState extends State<ReviewScreen>
    with SingleTickerProviderStateMixin {
  int _currentPageIndex = 0;
  bool _showCleaned = true;
  bool _showOverlayBoxes = true;
  bool _showBubblesDrawer = true;
  String _selectedExportFormat = 'png'; // 'png', 'jpg', 'webp', 'original'

  final TransformationController _transformController =
      TransformationController();

  BubbleItem? _selectedBubble;
  int? _selectedBubbleIndex;
  final TextEditingController _editTranslationController =
      TextEditingController();
  bool _isSavingBubble = false;
  bool _isActionInProgress = false;
  bool _isDownloading = false;

  // Cache buster map for live image re-renders
  final Map<String, String> _customCleanedUrls = {};

  @override
  void initState() {
    super.initState();
    if (currentPage.cleanedUrl == null) {
      _showCleaned = false;
    }
    _precacheCurrentImages();
  }

  void _precacheCurrentImages() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (currentPage.imageUrl.isNotEmpty) {
        precacheImage(
          NetworkImage(
            currentPage.imageUrl,
            headers: const {'ngrok-skip-browser-warning': 'true'},
          ),
          context,
        );
      }
      final cleanUrl = _getCleanUrl();
      if (cleanUrl != null && cleanUrl.isNotEmpty) {
        precacheImage(
          NetworkImage(
            cleanUrl,
            headers: const {'ngrok-skip-browser-warning': 'true'},
          ),
          context,
        );
      }
    });
  }

  String? _getCleanUrl() {
    return _customCleanedUrls[currentPage.imagePath] ?? currentPage.cleanedUrl;
  }

  PageResult get currentPage => widget.batchResponse.pages.isNotEmpty
      ? widget.batchResponse.pages[_currentPageIndex]
      : PageResult(
          imagePath: '',
          imageName: '',
          imageUrl: '',
          bubblesCount: 0,
          bubbles: [],
        );

  void _resetZoom() {
    _transformController.value = Matrix4.identity();
  }

  void _selectBubble(BubbleItem bubble, int index, {bool openSheet = false}) {
    if (_selectedBubble?.id == bubble.id && !openSheet) {
      _showEditBubbleSheet();
      return;
    }

    setState(() {
      _selectedBubble = bubble;
      _selectedBubbleIndex = index;
      _editTranslationController.text = bubble.assignedTranslation;
    });

    if (openSheet) {
      _showEditBubbleSheet();
    }
  }

  void _showEditBubbleSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surfaceDark,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            return Directionality(
              textDirection: TextDirection.rtl,
              child: Padding(
                padding: EdgeInsets.only(
                  left: 20,
                  right: 20,
                  top: 20,
                  bottom: MediaQuery.of(sheetContext).viewInsets.bottom + 20,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: AppTheme.accentEmerald,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                '#${_selectedBubble?.id ?? 1}',
                                style: const TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            const Text(
                              'تعديل وإجراءات الفقاعة',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                        IconButton(
                          icon: const Icon(Icons.close_rounded),
                          onPressed: () => Navigator.pop(sheetContext),
                        ),
                      ],
                    ),
                    if (_selectedBubble?.originalText.isNotEmpty == true) ...[
                      const SizedBox(height: 6),
                      Text(
                        'النص الأصلي (OCR): ${_selectedBubble?.originalText}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: Color(0xFF94A3B8),
                        ),
                      ),
                    ],
                    const SizedBox(height: 14),

                    // Granular Bubble Inpainting Actions
                    const Text(
                      'إجراءات تنظيف وتبييض هذه الفقاعة:',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFFCBD5E1),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        ActionChip(
                          avatar: const Icon(Icons.auto_fix_high_rounded,
                              size: 16, color: AppTheme.accentEmerald),
                          label: const Text('إعادة تنظيف بـ AI ✨'),
                          backgroundColor: AppTheme.cardDark,
                          onPressed: _isActionInProgress
                              ? null
                              : () => _handleBubbleCleanAction(
                                  'reclean_ai', sheetContext, setSheetState),
                        ),
                        ActionChip(
                          avatar: const Icon(Icons.format_paint_rounded,
                              size: 16, color: AppTheme.primaryCyan),
                          label: const Text('تبييض مسطح سريع ✍️'),
                          backgroundColor: AppTheme.cardDark,
                          onPressed: _isActionInProgress
                              ? null
                              : () => _handleBubbleCleanAction(
                                  'flat_white', sheetContext, setSheetState),
                        ),
                        ActionChip(
                          avatar: const Icon(Icons.undo_rounded,
                              size: 16, color: AppTheme.accentRose),
                          label: const Text('استعادة الرسم الأصلي ↩️'),
                          backgroundColor: AppTheme.cardDark,
                          onPressed: _isActionInProgress
                              ? null
                              : () => _handleBubbleCleanAction(
                                  'restore_original',
                                  sheetContext,
                                  setSheetState),
                        ),
                      ],
                    ),
                    const Divider(height: 24, color: AppTheme.borderDark),

                    // Translation Editing Section
                    const Text(
                      'الترجمة العربية المعينة:',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    TextField(
                      controller: _editTranslationController,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        hintText: 'اكتب أو عدّل الترجمة العربية هنا...',
                      ),
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: _isSavingBubble ? null : _saveBubbleEdit,
                        icon: _isSavingBubble
                            ? const SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Icon(Icons.check_circle_rounded),
                        label: const Text('حفظ التعديل وتحديث JSON'),
                      ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _handleBubbleCleanAction(
      String action, BuildContext sheetCtx, StateSetter setSheetState) async {
    if (_selectedBubbleIndex == null) return;

    setSheetState(() => _isActionInProgress = true);
    setState(() => _isActionInProgress = true);

    final res = await widget.apiService.executeBubbleCleaningAction(
      batchId: widget.batchResponse.batchId,
      pageKey: currentPage.imagePath,
      bubbleIndex: _selectedBubbleIndex!,
      action: action,
      dilation: 5,
    );

    if (!mounted) return;
    setSheetState(() => _isActionInProgress = false);
    setState(() {
      _isActionInProgress = false;
      if (res['success'] == true && res['cleaned_url'] != null) {
        _customCleanedUrls[currentPage.imagePath] = res['cleaned_url'];
        _showCleaned = true;
        _precacheCurrentImages();
      }
    });

    if (sheetCtx.mounted) {
      Navigator.pop(sheetCtx);
    }
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'تم تنفيذ العملية بنجاح! ✨'),
          backgroundColor: res['success'] == true
              ? AppTheme.accentEmerald
              : AppTheme.accentRose,
        ),
      );
    }
  }

  Future<void> _saveBubbleEdit() async {
    if (_selectedBubble == null || _selectedBubbleIndex == null) return;

    setState(() => _isSavingBubble = true);
    final newText = _editTranslationController.text.trim();

    final success = await widget.apiService.updateBubbleTranslation(
      batchId: widget.batchResponse.batchId,
      pageKey: currentPage.imagePath,
      bubbleIndex: _selectedBubbleIndex!,
      arabicText: newText,
    );

    if (!mounted) return;
    setState(() {
      _isSavingBubble = false;
      if (success) {
        _selectedBubble!.assignedTranslation = newText;
      }
    });

    Navigator.pop(context);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(success
            ? 'تم تحديث الفقاعة بنجاح! ✨'
            : 'فشل التحديث، يرجى المحاولة ثانية.'),
        backgroundColor:
            success ? AppTheme.accentEmerald : AppTheme.accentRose,
      ),
    );
  }

  Future<void> _triggerPcOpen() async {
    final res = await widget.apiService.triggerPcGui();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['success'] == true
              ? 'تم فتح واجهة البرنامج على الكمبيوتر بنجاح! 🖥️'
              : 'تعذر فتح البرنامج: ${res['message']}'),
          backgroundColor: res['success'] == true
              ? AppTheme.accentEmerald
              : AppTheme.accentRose,
        ),
      );
    }
  }

  Future<Directory> _getPublicDownloadDir() async {
    if (Platform.isAndroid) {
      final d = Directory('/storage/emulated/0/Download');
      if (await d.exists()) return d;
      final ext = await getExternalStorageDirectory();
      if (ext != null) return ext;
    }
    return await getApplicationDocumentsDirectory();
  }

  void _openSaveToPcDialog() {
    final rawName = currentPage.imageName;
    final defaultStem =
        rawName.contains('.') ? rawName.split('.').first : 'Chapter_Export';
    final folderController =
        TextEditingController(text: 'SmartCleaner_$defaultStem');
    bool saveCleaned = true;
    bool saveJson = true;

    showDialog(
      context: context,
      builder: (dlgCtx) {
        return StatefulBuilder(
          builder: (ctx, setDlgState) {
            return Directionality(
              textDirection: TextDirection.rtl,
              child: AlertDialog(
                backgroundColor: const Color(0xFF1E293B),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: const BorderSide(color: AppTheme.primaryBlue, width: 1.5),
                ),
                title: Row(
                  children: const [
                    Icon(Icons.desktop_windows_rounded,
                        color: AppTheme.primaryBlue),
                    SizedBox(width: 8),
                    Text(
                      'حفظ الفصل على الكمبيوتر',
                      style: TextStyle(
                          fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                content: SingleChildScrollView(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'اكتب اسم المجلد الذي سيتم إنشاؤه على الكمبيوتر:',
                        style:
                            TextStyle(fontSize: 12, color: Color(0xFF94A3B8)),
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: folderController,
                        style: const TextStyle(color: Colors.white, fontSize: 13),
                        decoration: InputDecoration(
                          prefixIcon: const Icon(Icons.folder_rounded,
                              color: AppTheme.primaryBlue),
                          hintText: 'مثال: Chapter 22 أو الفصل 1',
                          hintStyle: const TextStyle(color: Color(0xFF64748B)),
                          filled: true,
                          fillColor: const Color(0xFF0F172A),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide:
                                const BorderSide(color: AppTheme.borderDark),
                          ),
                          focusedBorder: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(10),
                            borderSide:
                                const BorderSide(color: AppTheme.primaryBlue),
                          ),
                        ),
                      ),
                      const SizedBox(height: 14),
                      const Text(
                        'خيارات التصدير للكمبيوتر:',
                        style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: Colors.white),
                      ),
                      const SizedBox(height: 4),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('حفظ الصور المنظفة (Cleaned Images)',
                            style: TextStyle(fontSize: 12)),
                        subtitle: Text(
                            'بالصيغة المحددة: ${_selectedExportFormat.toUpperCase()}',
                            style: const TextStyle(
                                fontSize: 10, color: Color(0xFF94A3B8))),
                        value: saveCleaned,
                        activeColor: AppTheme.accentEmerald,
                        onChanged: (v) =>
                            setDlgState(() => saveCleaned = v ?? true),
                      ),
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('حفظ ملفات TypeR JSON و project.ftr',
                            style: TextStyle(fontSize: 12)),
                        subtitle: const Text(
                            'لتجهيز السكريبت فوراً داخل الفوتوشوب',
                            style: TextStyle(
                                fontSize: 10, color: Color(0xFF94A3B8))),
                        value: saveJson,
                        activeColor: AppTheme.primaryCyan,
                        onChanged: (v) =>
                            setDlgState(() => saveJson = v ?? true),
                      ),
                      const SizedBox(height: 6),
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0F172A),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: AppTheme.borderDark),
                        ),
                        child: Row(
                          children: const [
                            Icon(Icons.info_outline_rounded,
                                size: 14, color: AppTheme.primaryCyan),
                            SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                'سيتم الحفظ في مجلد Downloads/SmartCleaner_Exports على جهاز الكمبيوتر.',
                                style: TextStyle(
                                    fontSize: 10, color: Color(0xFF94A3B8)),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                actions: [
                  TextButton(
                    onPressed: () => Navigator.pop(dlgCtx),
                    child: const Text('إلغاء',
                        style: TextStyle(color: Color(0xFF94A3B8))),
                  ),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.primaryBlue,
                      foregroundColor: Colors.white,
                    ),
                    icon: const Icon(Icons.save_rounded, size: 16),
                    label: const Text('💾 حفظ على الكمبيوتر'),
                    onPressed: () async {
                      final fName = folderController.text.trim();
                      if (fName.isEmpty) return;
                      Navigator.pop(dlgCtx);
                      _executeSaveToPc(
                        folderName: fName,
                        format: _selectedExportFormat,
                        saveCleaned: saveCleaned,
                        saveJson: saveJson,
                      );
                    },
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _executeSaveToPc({
    required String folderName,
    required String format,
    required bool saveCleaned,
    required bool saveJson,
  }) async {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
            'جاري تصدير وحفظ الفصل على الكمبيوتر في مجلد [$folderName]... ⏳'),
        backgroundColor: AppTheme.primaryBlue,
      ),
    );

    final res = await widget.apiService.saveBatchToPc(
      batchId: widget.batchResponse.batchId,
      folderName: folderName,
      format: format,
      saveCleaned: saveCleaned,
      saveJson: saveJson,
    );

    if (mounted) {
      if (res['success'] == true) {
        showDialog(
          context: context,
          builder: (ctx) => Directionality(
            textDirection: TextDirection.rtl,
            child: AlertDialog(
              backgroundColor: const Color(0xFF1E293B),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side:
                    const BorderSide(color: AppTheme.accentEmerald, width: 1.5),
              ),
              title: Row(
                children: const [
                  Icon(Icons.check_circle_rounded,
                      color: AppTheme.accentEmerald),
                  SizedBox(width: 8),
                  Text('تم الحفظ على الكمبيوتر بنجاح! 🎉',
                      style:
                          TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
                ],
              ),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(res['message']?.toString() ?? 'تم حفظ الملفات'),
                  const SizedBox(height: 10),
                  const Text('المسار على الكمبيوتر:',
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF94A3B8))),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTheme.borderDark),
                    ),
                    child: SelectableText(
                      res['saved_path']?.toString() ?? '',
                      style: const TextStyle(
                          fontSize: 11,
                          color: AppTheme.accentEmerald,
                          fontFamily: 'monospace'),
                    ),
                  ),
                ],
              ),
              actions: [
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                      backgroundColor: AppTheme.accentEmerald),
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text('ممتاز',
                      style: TextStyle(color: Colors.white)),
                ),
              ],
            ),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('تعذر الحفظ على الكمبيوتر: ${res['message']}'),
            backgroundColor: AppTheme.accentRose,
          ),
        );
      }
    }
  }

  void _showDownloadsSheet() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surfaceDark,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return StatefulBuilder(
          builder: (dCtx, setDState) {
            final dls = widget.batchResponse.downloads;
            final isPageCleaned = _getCleanUrl() != null;

            return Directionality(
              textDirection: TextDirection.rtl,
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'تنزيل وحفظ الصور والملفات 📥',
                          style: TextStyle(
                              fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        IconButton(
                          icon: const Icon(Icons.close_rounded),
                          onPressed: () => Navigator.pop(dCtx),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),

                    // Format Selection Row
                    const Text(
                      'صيغة تصدير الصور المنظفة:',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF94A3B8),
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        _buildFormatChip('PNG', 'png', setDState),
                        const SizedBox(width: 6),
                        _buildFormatChip('JPG', 'jpg', setDState),
                        const SizedBox(width: 6),
                        _buildFormatChip('WEBP', 'webp', setDState),
                        const SizedBox(width: 6),
                        _buildFormatChip('الأصلية', 'original', setDState),
                      ],
                    ),
                    const Divider(height: 20, color: AppTheme.borderDark),

                    // 0. Save Directly to PC Folder!
                    Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            AppTheme.primaryBlue.withValues(alpha: 0.25),
                            AppTheme.primaryCyan.withValues(alpha: 0.15),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(12),
                        border:
                            Border.all(color: AppTheme.primaryBlue, width: 1.5),
                      ),
                      child: ListTile(
                        leading: const Icon(Icons.desktop_windows_rounded,
                            color: AppTheme.primaryCyan, size: 28),
                        title: const Text(
                          'حفظ الفصل مباشرة على الكمبيوتر 🖥️',
                          style: TextStyle(
                              fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                        subtitle: const Text(
                          'حفظ الصور والنتائج في مجلد مخصص داخل جهاز الكمبيوتر',
                          style:
                              TextStyle(fontSize: 11, color: Color(0xFF94A3B8)),
                        ),
                        trailing: const Icon(Icons.arrow_back_ios_new_rounded,
                            size: 16, color: AppTheme.primaryCyan),
                        onTap: () {
                          Navigator.pop(dCtx);
                          _openSaveToPcDialog();
                        },
                      ),
                    ),

                    // 1. Download Current Single Page (Uncompressed Image directly!)
                    if (isPageCleaned)
                      ListTile(
                        leading: const Icon(Icons.image_outlined,
                            color: AppTheme.primaryCyan, size: 28),
                        title: Text(
                            'حفظ هذه الصفحة الحالية مباشرة (${_selectedExportFormat.toUpperCase()})'),
                        subtitle: Text(
                            'حفظ صورة مفردة باسمها الأصلي (${currentPage.imageName.split('.').first}.${_selectedExportFormat == 'original' ? currentPage.imageName.split('.').last : _selectedExportFormat}) في التنزيلات'),
                        trailing: const Icon(Icons.file_download_outlined),
                        onTap: () {
                          Navigator.pop(dCtx);
                          _downloadSinglePageImage();
                        },
                      ),

                    // 2. Download All Cleaned Pages - Unzipped / Extracted directly
                    if (dls.cleanedZip != null) ...[
                      ListTile(
                        leading: const Icon(Icons.folder_open_rounded,
                            color: AppTheme.accentEmerald, size: 28),
                        title: Text(
                            'حفظ جميع الصفحات مفكوكة في مجلد (${_selectedExportFormat.toUpperCase()})'),
                        subtitle: const Text(
                            'تنزيل وفك ضغط جميع الصور تلقائياً في مجلد الصور/التنزيلات بأسمائها الأصلية'),
                        trailing: const Icon(Icons.unarchive_rounded),
                        onTap: () {
                          Navigator.pop(dCtx);
                          _downloadAndUnzipCleanedImages();
                        },
                      ),
                      ListTile(
                        leading: const Icon(Icons.folder_zip_outlined,
                            color: Color(0xFF94A3B8), size: 28),
                        title: Text('تحميل الصفحات كملف مضغوط (ZIP)'),
                        subtitle: Text(
                            'حفظ ملف مضغوط واحد بصيغة ${_selectedExportFormat.toUpperCase()}'),
                        trailing: const Icon(Icons.download_rounded),
                        onTap: () {
                          Navigator.pop(dCtx);
                          final cleanUrl =
                              '${dls.cleanedZip!}?format=$_selectedExportFormat';
                          _downloadRawZip(cleanUrl,
                              'Cleaned_Images_${_selectedExportFormat.toUpperCase()}.zip');
                        },
                      ),
                    ],

                    const Divider(height: 16, color: AppTheme.borderDark),

                    if (dls.jsonZip != null)
                      ListTile(
                        leading: const Icon(Icons.code_rounded,
                            color: AppTheme.primaryCyan),
                        title: const Text('تحميل ملفات TypeR JSON (ZIP)'),
                        subtitle: const Text('ملفات JSON الجاهزة لسكريبت TypeR'),
                        trailing: const Icon(Icons.download_rounded),
                        onTap: () {
                          Navigator.pop(dCtx);
                          _downloadRawZip(dls.jsonZip!, 'TypeR_JSONs.zip');
                        },
                      ),
                    if (dls.projectFtr != null)
                      ListTile(
                        leading: const Icon(Icons.folder_zip_rounded,
                            color: AppTheme.primaryBlue),
                        title: const Text('تحميل ملف المشروع (project.cln / .ftr)'),
                        subtitle: const Text('لفتحه في SmartCleaner على الكمبيوتر'),
                        trailing: const Icon(Icons.download_rounded),
                        onTap: () {
                          Navigator.pop(dCtx);
                          _downloadRawZip(dls.projectFtr!, 'project.ftr');
                        },
                      ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildFormatChip(String label, String value, StateSetter setDState) {
    final isSel = _selectedExportFormat == value;
    return ChoiceChip(
      selected: isSel,
      label: Text(
        label,
        style: TextStyle(
          fontSize: 11,
          fontWeight: isSel ? FontWeight.bold : FontWeight.normal,
          color: isSel ? Colors.black : Colors.white,
        ),
      ),
      selectedColor: AppTheme.primaryCyan,
      backgroundColor: AppTheme.cardDark,
      onSelected: (val) {
        if (val) {
          setDState(() => _selectedExportFormat = value);
          setState(() => _selectedExportFormat = value);
        }
      },
    );
  }

  // 1. Download Single Cleaned Page Directly as an Uncompressed Image
  Future<void> _downloadSinglePageImage() async {
    if (_isDownloading) return;
    setState(() => _isDownloading = true);

    final rawName = currentPage.imageName;
    final baseStem = rawName.contains('.') ? rawName.split('.').first : rawName;
    final ext = _selectedExportFormat == 'original'
        ? (rawName.contains('.') ? rawName.split('.').last : 'jpg')
        : _selectedExportFormat;
    final targetFilename = '$baseStem.$ext';

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('جاري تنزيل الصورة $targetFilename... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );

    try {
      final downloadUrl =
          '${widget.apiService.baseUrl}/api/batch/${widget.batchResponse.batchId}/download-page/$rawName?format=$_selectedExportFormat';
      final dio = Dio();
      final res = await dio.get(
        downloadUrl,
        options: Options(
          responseType: ResponseType.bytes,
          headers: {'ngrok-skip-browser-warning': 'true'},
        ),
      );

      if (res.statusCode == 200 && res.data != null) {
        final dlDir = await _getPublicDownloadDir();
        final outDir = Directory('${dlDir.path}/SmartCleaner_Images');
        if (!await outDir.exists()) {
          await outDir.create(recursive: true);
        }

        final targetFile = File('${outDir.path}/$targetFilename');
        await targetFile.writeAsBytes(res.data as List<int>);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content:
                  Text('تم حفظ الصورة بنجاح! 🖼️\nالمسار: ${targetFile.path}'),
              duration: const Duration(seconds: 4),
              backgroundColor: AppTheme.accentEmerald,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('تعذر تنزيل الصورة: $e'),
            backgroundColor: AppTheme.accentRose,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isDownloading = false);
    }
  }

  // 2. Download and Automatically Unzip/Extract All Cleaned Images
  Future<void> _downloadAndUnzipCleanedImages() async {
    if (_isDownloading) return;
    setState(() => _isDownloading = true);

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('جاري تنزيل وفك ضغط جميع الصفحات تلقائياً... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );

    try {
      final cleanZipUrl =
          '${widget.batchResponse.downloads.cleanedZip!}?format=$_selectedExportFormat';
      final dio = Dio();
      final res = await dio.get(
        cleanZipUrl,
        options: Options(
          responseType: ResponseType.bytes,
          headers: {'ngrok-skip-browser-warning': 'true'},
        ),
      );

      if (res.statusCode == 200 && res.data != null) {
        final bytes = res.data as List<int>;
        final archive = ZipDecoder().decodeBytes(bytes);

        final dlDir = await _getPublicDownloadDir();
        final outDir = Directory(
            '${dlDir.path}/SmartCleaner_Cleaned_${DateTime.now().millisecondsSinceEpoch.toString().substring(6)}');
        if (!await outDir.exists()) {
          await outDir.create(recursive: true);
        }

        int extractedCount = 0;
        for (final file in archive) {
          if (file.isFile) {
            // Restore clean page name (e.g. clean_08.png -> 08.png)
            final rawCleanName = file.name.replaceAll('clean_', '');
            final outFile = File('${outDir.path}/$rawCleanName');
            await outFile.writeAsBytes(file.content as List<int>);
            extractedCount++;
          }
        }

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  'تم فك وحفظ $extractedCount صفحة بصيغة ${_selectedExportFormat.toUpperCase()} بنجاح! 🎉\nالمجلد: ${outDir.path}'),
              duration: const Duration(seconds: 5),
              backgroundColor: AppTheme.accentEmerald,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('حدث خطأ أثناء فك الضغط والتنزيل: $e'),
            backgroundColor: AppTheme.accentRose,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isDownloading = false);
    }
  }

  // 3. Raw ZIP Download
  Future<void> _downloadRawZip(String url, String filename) async {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('جاري بدء تحميل $filename... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );
    try {
      final dio = Dio();
      final res = await dio.get(
        url,
        options: Options(
          responseType: ResponseType.bytes,
          headers: {'ngrok-skip-browser-warning': 'true'},
        ),
      );
      if (res.statusCode == 200 && res.data != null) {
        final dlDir = await _getPublicDownloadDir();
        final outFile = File('${dlDir.path}/$filename');
        await outFile.writeAsBytes(res.data as List<int>);

        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content:
                  Text('تم تنزيل $filename بنجاح! ✅\nالمسار: ${outFile.path}'),
              backgroundColor: AppTheme.accentEmerald,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('تعذر التنزيل: $e'),
            backgroundColor: AppTheme.accentRose,
          ),
        );
      }
    }
  }

  @override
  void dispose() {
    _transformController.dispose();
    _editTranslationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cleanUrl = _getCleanUrl();
    final hasCleaned = cleanUrl != null;
    final displayUrl =
        (_showCleaned && hasCleaned) ? cleanUrl : currentPage.imageUrl;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          'صفحة ${_currentPageIndex + 1} من ${widget.batchResponse.pagesCount}',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        actions: [
          // Toggle Overlay Boxes Button
          IconButton(
            tooltip:
                _showOverlayBoxes ? 'إخفاء حدود الفقاعات' : 'إظهار حدود الفقاعات',
            icon: Icon(
              _showOverlayBoxes ? Icons.grid_on_rounded : Icons.grid_off_rounded,
              color: _showOverlayBoxes
                  ? AppTheme.primaryCyan
                  : const Color(0xFF64748B),
            ),
            onPressed: () =>
                setState(() => _showOverlayBoxes = !_showOverlayBoxes),
          ),

          // Download Action
          IconButton(
            tooltip: 'تنزيل الملفات والنتائج',
            icon: const Icon(Icons.download_rounded,
                color: AppTheme.accentEmerald),
            onPressed: _showDownloadsSheet,
          ),

          // Open PC GUI
          IconButton(
            tooltip: 'فتح على الكمبيوتر',
            icon: const Icon(Icons.desktop_windows_rounded,
                color: AppTheme.primaryBlue),
            onPressed: _triggerPcOpen,
          ),
        ],
      ),
      body: Directionality(
        textDirection: TextDirection.rtl,
        child: Column(
          children: [
            // Page Selector Chips Bar
            Container(
              height: 48,
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              color: AppTheme.surfaceDark,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: widget.batchResponse.pagesCount,
                itemBuilder: (ctx, idx) {
                  final isSelected = idx == _currentPageIndex;
                  final p = widget.batchResponse.pages[idx];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3),
                    child: ChoiceChip(
                      selected: isSelected,
                      label: Text(
                        'صفحة ${idx + 1} (${p.bubblesCount})',
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight:
                              isSelected ? FontWeight.bold : FontWeight.normal,
                          color: isSelected ? Colors.black : Colors.white,
                        ),
                      ),
                      selectedColor: AppTheme.primaryCyan,
                      backgroundColor: AppTheme.cardDark,
                      onSelected: (val) {
                        if (val) {
                          setState(() {
                            _currentPageIndex = idx;
                            _resetZoom();
                            _selectedBubble = null;
                            _selectedBubbleIndex = null;
                            if (p.cleanedUrl == null) {
                              _showCleaned = false;
                            }
                          });
                          _precacheCurrentImages();
                        }
                      },
                    ),
                  );
                },
              ),
            ),

            // Main Interactive Manga Viewer (Naturally Scaled without any distortion!)
            Expanded(
              child: Stack(
                alignment: Alignment.center,
                children: [
                  Container(
                    color: const Color(0xFF0F172A),
                    width: double.infinity,
                    height: double.infinity,
                    child: InteractiveViewer(
                      transformationController: _transformController,
                      minScale: 0.1,
                      maxScale: 12.0,
                      boundaryMargin: const EdgeInsets.all(2500.0),
                      clipBehavior: Clip.none,
                      child: Center(
                        child: _MangaPageView(
                          key: ValueKey(displayUrl),
                          imageUrl: displayUrl,
                          bubbles: currentPage.bubbles,
                          selectedBubble: _selectedBubble,
                          showOverlayBoxes: _showOverlayBoxes,
                          onBubbleTap: (b, idx) =>
                              _selectBubble(b, idx, openSheet: false),
                        ),
                      ),
                    ),
                  ),

                  // Floating Cleaned / Original Segmented Toggle Pill (Instant Switch)
                  if (hasCleaned)
                    Positioned(
                      top: 14,
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.75),
                          borderRadius: BorderRadius.circular(30),
                          border: Border.all(
                            color: _showCleaned
                                ? AppTheme.accentEmerald
                                : AppTheme.primaryCyan,
                            width: 1.5,
                          ),
                          boxShadow: const [
                            BoxShadow(
                              color: Colors.black45,
                              blurRadius: 10,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            GestureDetector(
                              onTap: () => setState(() => _showCleaned = true),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 14, vertical: 6),
                                decoration: BoxDecoration(
                                  color: _showCleaned
                                      ? AppTheme.accentEmerald
                                      : Colors.transparent,
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Row(
                                  children: [
                                    Icon(
                                      Icons.cleaning_services_rounded,
                                      size: 16,
                                      color: _showCleaned
                                          ? Colors.black
                                          : Colors.white,
                                    ),
                                    const SizedBox(width: 4),
                                    Text(
                                      'المنظفة ✨',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.bold,
                                        color: _showCleaned
                                            ? Colors.black
                                            : Colors.white,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                            GestureDetector(
                              onTap: () => setState(() => _showCleaned = false),
                              child: Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 14, vertical: 6),
                                decoration: BoxDecoration(
                                  color: !_showCleaned
                                      ? AppTheme.primaryCyan
                                      : Colors.transparent,
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Row(
                                  children: [
                                    Icon(
                                      Icons.image_rounded,
                                      size: 16,
                                      color: !_showCleaned
                                          ? Colors.black
                                          : Colors.white,
                                    ),
                                    const SizedBox(width: 4),
                                    Text(
                                      'الأصلية 🖼️',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontWeight: FontWeight.bold,
                                        color: !_showCleaned
                                            ? Colors.black
                                            : Colors.white,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),

                  // Floating Selected Bubble Quick Action Card (Non-intrusive!)
                  if (_selectedBubble != null)
                    Positioned(
                      bottom: 12,
                      left: 12,
                      right: 65,
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 6),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1E293B).withValues(alpha: 0.95),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                              color: AppTheme.accentEmerald, width: 1.5),
                          boxShadow: const [
                            BoxShadow(
                              color: Colors.black54,
                              blurRadius: 10,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                        child: Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: AppTheme.accentEmerald,
                                borderRadius: BorderRadius.circular(6),
                              ),
                              child: Text(
                                '#${_selectedBubble!.id}',
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.black,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _selectedBubble!.assignedTranslation.isNotEmpty
                                    ? _selectedBubble!.assignedTranslation
                                    : (_selectedBubble!.originalText.isNotEmpty
                                        ? _selectedBubble!.originalText
                                        : 'فقاعة محددة'),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                            const SizedBox(width: 6),
                            ElevatedButton.icon(
                              style: ElevatedButton.styleFrom(
                                backgroundColor: AppTheme.accentEmerald,
                                foregroundColor: Colors.black,
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 4),
                                visualDensity: VisualDensity.compact,
                              ),
                              icon: const Icon(Icons.tune_rounded, size: 14),
                              label: const Text(
                                'الخيارات ⚙️',
                                style: TextStyle(
                                    fontSize: 11, fontWeight: FontWeight.bold),
                              ),
                              onPressed: _showEditBubbleSheet,
                            ),
                            const SizedBox(width: 2),
                            IconButton(
                              tooltip: 'إلغاء التحديد',
                              icon: const Icon(Icons.close_rounded,
                                  size: 16, color: Color(0xFF94A3B8)),
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(),
                              onPressed: () {
                                setState(() {
                                  _selectedBubble = null;
                                  _selectedBubbleIndex = null;
                                });
                              },
                            ),
                          ],
                        ),
                      ),
                    ),

                  // Floating Reset Zoom Button
                  Positioned(
                    bottom: 14,
                    right: 14,
                    child: FloatingActionButton.small(
                      heroTag: 'reset_zoom_btn',
                      backgroundColor: Colors.black.withValues(alpha: 0.7),
                      foregroundColor: Colors.white,
                      tooltip: 'إعادة ضبط التكبير (1x)',
                      onPressed: _resetZoom,
                      child: const Icon(Icons.aspect_ratio_rounded, size: 20),
                    ),
                  ),
                ],
              ),
            ),

            // Bottom Navigation & Bubbles Bar
            Container(
              color: AppTheme.surfaceDark,
              child: Column(
                children: [
                  // Quick Prev / Next Page Buttons
                  Padding(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 6),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        ElevatedButton.icon(
                          onPressed: _currentPageIndex > 0
                              ? () {
                                  setState(() {
                                    _currentPageIndex--;
                                    _resetZoom();
                                    _precacheCurrentImages();
                                  });
                                }
                              : null,
                          icon: const Icon(Icons.arrow_forward_ios_rounded,
                              size: 14),
                          label: const Text('السابقة'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppTheme.cardDark,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                          ),
                        ),
                        GestureDetector(
                          onTap: () => setState(
                              () => _showBubblesDrawer = !_showBubblesDrawer),
                          child: Row(
                            children: [
                              Icon(
                                _showBubblesDrawer
                                    ? Icons.keyboard_arrow_down_rounded
                                    : Icons.keyboard_arrow_up_rounded,
                                color: AppTheme.primaryCyan,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${currentPage.bubblesCount} فقاعة',
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: AppTheme.primaryCyan,
                                ),
                              ),
                            ],
                          ),
                        ),
                        ElevatedButton.icon(
                          onPressed: _currentPageIndex <
                                  widget.batchResponse.pagesCount - 1
                              ? () {
                                  setState(() {
                                    _currentPageIndex++;
                                    _resetZoom();
                                    _precacheCurrentImages();
                                  });
                                }
                              : null,
                          icon: const Icon(Icons.arrow_back_ios_rounded,
                              size: 14),
                          label: const Text('التالية'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppTheme.cardDark,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Collapsible Bubbles List
                  if (_showBubblesDrawer && currentPage.bubbles.isNotEmpty)
                    SizedBox(
                      height: 90,
                      child: ListView.builder(
                        scrollDirection: Axis.horizontal,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 4),
                        itemCount: currentPage.bubbles.length,
                        itemBuilder: (ctx, idx) {
                          final b = currentPage.bubbles[idx];
                          final isSel = _selectedBubble?.id == b.id;
                          return GestureDetector(
                            onTap: () => _selectBubble(b, idx, openSheet: false),
                            child: Container(
                              width: 140,
                              margin: const EdgeInsets.only(left: 8),
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: isSel
                                    ? AppTheme.accentEmerald
                                        .withValues(alpha: 0.25)
                                    : AppTheme.cardDark,
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(
                                  color: isSel
                                      ? AppTheme.accentEmerald
                                      : AppTheme.borderDark,
                                  width: isSel ? 2.0 : 1,
                                ),
                                boxShadow: isSel
                                    ? [
                                        BoxShadow(
                                          color: AppTheme.accentEmerald
                                              .withValues(alpha: 0.3),
                                          blurRadius: 8,
                                          spreadRadius: 1,
                                        ),
                                      ]
                                    : null,
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Row(
                                    mainAxisAlignment:
                                        MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        '#${b.id}',
                                        style: TextStyle(
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                          color: isSel
                                              ? AppTheme.accentEmerald
                                              : AppTheme.primaryCyan,
                                        ),
                                      ),
                                      if (isSel)
                                        const Icon(
                                          Icons.visibility_rounded,
                                          size: 14,
                                          color: AppTheme.accentEmerald,
                                        ),
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    b.assignedTranslation.isEmpty
                                        ? (b.originalText.isEmpty
                                            ? 'فقاعة بدون نص'
                                            : b.originalText)
                                        : b.assignedTranslation,
                                    maxLines: 2,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontSize: 11),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Manga Page View that dynamically loads natural image dimensions and fits
/// with 100% natural aspect ratio (Zero stretching / Zero squishing)
class _MangaPageView extends StatefulWidget {
  final String imageUrl;
  final List<BubbleItem> bubbles;
  final BubbleItem? selectedBubble;
  final bool showOverlayBoxes;
  final Function(BubbleItem, int) onBubbleTap;

  const _MangaPageView({
    super.key,
    required this.imageUrl,
    required this.bubbles,
    required this.selectedBubble,
    required this.showOverlayBoxes,
    required this.onBubbleTap,
  });

  @override
  State<_MangaPageView> createState() => _MangaPageViewState();
}

class _MangaPageViewState extends State<_MangaPageView> {
  ImageStream? _imageStream;
  ImageInfo? _imageInfo;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolveImage();
  }

  @override
  void didUpdateWidget(covariant _MangaPageView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.imageUrl != widget.imageUrl) {
      _resolveImage();
    }
  }

  void _resolveImage() {
    final imageProvider = NetworkImage(
      widget.imageUrl,
      headers: const {'ngrok-skip-browser-warning': 'true'},
    );
    _imageStream?.removeListener(ImageStreamListener(_updateImageInfo));
    _imageStream =
        imageProvider.resolve(createLocalImageConfiguration(context));
    _imageStream?.addListener(ImageStreamListener(_updateImageInfo));
  }

  void _updateImageInfo(ImageInfo info, bool _) {
    if (mounted) {
      setState(() {
        _imageInfo = info;
      });
    }
  }

  @override
  void dispose() {
    _imageStream?.removeListener(ImageStreamListener(_updateImageInfo));
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_imageInfo == null) {
      return const SizedBox(
        width: 150,
        height: 250,
        child: Center(
          child: CircularProgressIndicator(
            color: AppTheme.primaryCyan,
            strokeWidth: 3,
          ),
        ),
      );
    }

    final naturalWidth = _imageInfo!.image.width.toDouble();
    final naturalHeight = _imageInfo!.image.height.toDouble();

    return FittedBox(
      fit: BoxFit.contain,
      alignment: Alignment.center,
      child: SizedBox(
        width: naturalWidth,
        height: naturalHeight,
        child: Stack(
          fit: StackFit.expand,
          children: [
            // Exact Raw Image Frame
            RawImage(
              image: _imageInfo!.image,
              fit: BoxFit.fill,
              width: naturalWidth,
              height: naturalHeight,
            ),

            // 1:1 Pixel-Perfect Bubbles Overlay
            if (widget.showOverlayBoxes || widget.selectedBubble != null)
              Stack(
                children: widget.bubbles.asMap().entries.map((entry) {
                  final idx = entry.key;
                  final b = entry.value;
                  final isSel = widget.selectedBubble?.id == b.id;

                  if (!widget.showOverlayBoxes && !isSel) {
                    return const SizedBox.shrink();
                  }

                  final bx = b.bounds.isNotEmpty ? b.bounds[0] : 0.0;
                  final by = b.bounds.length > 1 ? b.bounds[1] : 0.0;
                  final bw = b.bounds.length > 2 ? b.bounds[2] : 50.0;
                  final bh = b.bounds.length > 3 ? b.bounds[3] : 50.0;

                  return Positioned(
                    left: bx,
                    top: by,
                    width: bw,
                    height: bh,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => widget.onBubbleTap(b, idx),
                      child: Container(
                        decoration: BoxDecoration(
                          color: isSel
                              ? AppTheme.accentEmerald.withValues(alpha: 0.35)
                              : AppTheme.primaryCyan.withValues(alpha: 0.12),
                          border: Border.all(
                            color: isSel
                                ? AppTheme.accentEmerald
                                : AppTheme.primaryCyan,
                            width: isSel ? 4.0 : 1.8,
                          ),
                          borderRadius: BorderRadius.circular(4),
                          boxShadow: isSel
                              ? [
                                  BoxShadow(
                                    color: AppTheme.accentEmerald
                                        .withValues(alpha: 0.6),
                                    blurRadius: 16,
                                    spreadRadius: 3,
                                  ),
                                ]
                              : null,
                        ),
                        child: Align(
                          alignment: Alignment.topRight,
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: isSel
                                  ? AppTheme.accentEmerald
                                  : Colors.black87,
                              borderRadius: const BorderRadius.only(
                                bottomLeft: Radius.circular(4),
                                topRight: Radius.circular(3),
                              ),
                            ),
                            child: Text(
                              '#${b.id}',
                              style: TextStyle(
                                fontSize: isSel ? 14 : 10,
                                fontWeight: FontWeight.bold,
                                color: isSel ? Colors.black : Colors.white,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                }).toList(),
              ),
          ],
        ),
      ),
    );
  }
}
