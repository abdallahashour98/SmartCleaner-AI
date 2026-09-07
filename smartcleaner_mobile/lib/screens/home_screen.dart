import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';
import '../services/api_service.dart';
import '../models/batch_model.dart';
import '../theme/app_theme.dart';
import 'settings_screen.dart';
import 'review_screen.dart';

class HomeScreen extends StatefulWidget {
  final ApiService apiService;

  const HomeScreen({super.key, required this.apiService});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  // Input Mode: 0 = Local Phone Images, 1 = Google Drive / Cloud URL
  int _inputMode = 0;
  final List<File> _selectedImages = [];
  final TextEditingController _chapterUrlController = TextEditingController();

  File? _selectedScriptFile;
  String? _inlineScriptText;

  // Processing Options
  bool _fastMode = false;
  bool _cleanImages = true;
  bool _openPcGui = false;
  bool _snapToBubbles = true;

  // Server Status
  ServerHealth? _health;
  bool _isProcessing = false;

  // Granular Live Progress
  Timer? _progressPollTimer;
  Timer? _elapsedTimer;
  int _elapsedSeconds = 0;

  double _livePercent = 0.0;
  String _liveStep = 'جاري التحضير...';
  String _liveDetail = '';
  int _liveCurrentPage = 0;
  int _liveTotalPages = 0;
  String _liveImageName = '';
  String _livePhase = 'upload';

  @override
  void initState() {
    super.initState();
    _chapterUrlController.addListener(() {
      if (mounted) setState(() {});
    });
    _checkServer();
  }

  @override
  void dispose() {
    _chapterUrlController.dispose();
    _progressPollTimer?.cancel();
    _elapsedTimer?.cancel();
    super.dispose();
  }

  Map<String, dynamic> _detectUrlInfo(String rawUrl) {
    final url = rawUrl.trim().toLowerCase();
    if (url.isEmpty) {
      return {
        'type': 'empty',
        'label': 'يرجى إدخال الرابط',
        'icon': Icons.link_rounded,
        'color': const Color(0xFF64748B),
      };
    }
    if (url.contains('drive.google.com') || url.contains('docs.google.com')) {
      if (url.contains('/folders/') || (url.contains('id=') && !url.contains('/file/d/'))) {
        return {
          'type': 'gdrive_folder',
          'label': 'مجلد Google Drive كامل 📂',
          'icon': Icons.folder_shared_rounded,
          'color': AppTheme.primaryCyan,
        };
      }
      return {
        'type': 'gdrive_file',
        'label': 'ملف Google Drive 📄',
        'icon': Icons.insert_drive_file_rounded,
        'color': AppTheme.primaryCyan,
      };
    }
    if (url.contains('dropbox.com')) {
      return {
        'type': 'dropbox',
        'label': 'Dropbox أرشيف 📦',
        'icon': Icons.cloud_download_rounded,
        'color': const Color(0xFF38BDF8),
      };
    }
    if (url.endsWith('.zip') || url.endsWith('.cbz') || url.endsWith('.rar') || url.endsWith('.7z')) {
      return {
        'type': 'archive',
        'label': 'ملف أرشيف مانجا مضغوط 📦',
        'icon': Icons.archive_rounded,
        'color': AppTheme.accentEmerald,
      };
    }
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return {
        'type': 'direct_url',
        'label': 'رابط سحابي مباشر 🌐',
        'icon': Icons.link_rounded,
        'color': const Color(0xFFA855F7),
      };
    }
    return {
      'type': 'unknown',
      'label': 'رابط غير معروف (تأكد من كتابة http/https)',
      'icon': Icons.warning_amber_rounded,
      'color': AppTheme.accentRose,
    };
  }

  Future<void> _pasteFromClipboard() async {
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      if (data != null && data.text != null && data.text!.trim().isNotEmpty) {
        setState(() {
          _chapterUrlController.text = data.text!.trim();
        });
        _showSnack('تم لصق الرابط بنجاح! 📋');
      } else {
        _showSnack('الحافظة فارغة أو لا تحتوي على نص', isError: true);
      }
    } catch (e) {
      _showSnack('تعذر القراءة من الحافظة: $e', isError: true);
    }
  }

  Future<void> _checkServer() async {
    final health = await widget.apiService.checkHealth();
    if (health.isOnline) {
      final pcConfig = await widget.apiService.fetchPcConfig();
      if (pcConfig != null && mounted) {
        setState(() {
          _fastMode = pcConfig['fast_mode'] ?? _fastMode;
          _cleanImages = pcConfig['iopaint_enabled'] ?? _cleanImages;
          _snapToBubbles = pcConfig['snap_to_bubbles'] ?? _snapToBubbles;
        });
      }
    }
    if (mounted) {
      setState(() {
        _health = health;
      });
    }
  }

  void _syncOptionToPc(String key, dynamic value) {
    widget.apiService.savePcConfig({key: value});
  }

  Future<void> _pickImages() async {
    try {
      final files = await FilePickerPlatform.instance.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'],
      );

      if (files.isNotEmpty) {
        setState(() {
          for (final f in files) {
            if (f.path != null) {
              final file = File(f.path!);
              if (!_selectedImages.any((img) => img.path == file.path)) {
                _selectedImages.add(file);
              }
            }
          }
        });
      }
    } catch (e) {
      _showSnack('تعذر اختيار الصور: $e', isError: true);
    }
  }

  Future<void> _pickScriptFile() async {
    try {
      final files = await FilePickerPlatform.instance.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['txt', 'docx', 'doc'],
      );

      if (files.isNotEmpty && files.first.path != null) {
        setState(() {
          _selectedScriptFile = File(files.first.path!);
          _inlineScriptText = null;
        });
      }
    } catch (e) {
      _showSnack('تعذر اختيار ملف الترجمة: $e', isError: true);
    }
  }

  void _openInlineScriptDialog() {
    final controller = TextEditingController(text: _inlineScriptText ?? '');
    showDialog(
      context: context,
      builder: (ctx) {
        return Directionality(
          textDirection: TextDirection.rtl,
          child: AlertDialog(
            title: const Text('كتابة نص الترجمة مباشرة'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'الصق نص الترجمة العربية هنا سطر بسطر:',
                  style: TextStyle(fontSize: 12, color: Color(0xFF94A3B8)),
                ),
                const SizedBox(height: 10),
                TextField(
                  controller: controller,
                  maxLines: 8,
                  decoration: const InputDecoration(
                    hintText:
                        'السطر الأول...\nالسطر الثاني...\nالسطر الثالث...',
                  ),
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton(
                    onPressed: () {
                      final txt = controller.text.trim();
                      if (txt.isNotEmpty) {
                        setState(() {
                          _inlineScriptText = txt;
                          _selectedScriptFile = null;
                        });
                        Navigator.pop(ctx);
                        _showSnack('تم تعيين نص الترجمة بنجاح! 📝');
                      }
                    },
                    child: const Text('حفظ النص'),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _startLiveProgressPolling() {
    _elapsedSeconds = 0;
    _elapsedTimer?.cancel();
    _elapsedTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted || !_isProcessing) {
        timer.cancel();
        return;
      }
      setState(() => _elapsedSeconds++);
    });
  }

  void _stopLiveProgressPolling() {
    _progressPollTimer?.cancel();
    _elapsedTimer?.cancel();
  }

  void _handleLiveProgressUpdate(Map<String, dynamic> prog) {
    if (!mounted || !_isProcessing) return;
    setState(() {
      final p = (prog['percent'] is num)
          ? (prog['percent'] as num).toDouble()
          : _livePercent;
      if (p > _livePercent) {
        _livePercent = p;
      }
      _liveStep = prog['step']?.toString() ?? _liveStep;
      _liveDetail = prog['detail']?.toString() ?? _liveDetail;
      _liveCurrentPage = (prog['current_page'] is num)
          ? (prog['current_page'] as num).toInt()
          : _liveCurrentPage;
      _liveTotalPages = (prog['total_pages'] is num)
          ? (prog['total_pages'] as num).toInt()
          : _liveTotalPages;
      _liveImageName = prog['current_image']?.toString() ?? _liveImageName;
      _livePhase = prog['phase']?.toString() ?? _livePhase;
    });
  }

  Future<void> _startProcessing() async {
    final isUrlMode = _inputMode == 1;
    final chapterUrl = _chapterUrlController.text.trim();

    if (isUrlMode && chapterUrl.isEmpty) {
      _showSnack('يرجى إدخال أو لصق رابط Google Drive أو الفصل أولاً 🔗', isError: true);
      return;
    }

    if (!isUrlMode && _selectedImages.isEmpty) {
      _showSnack('يرجى اختيار صور المانجا أولاً 🖼️', isError: true);
      return;
    }

    final bool hasScript = _selectedScriptFile != null ||
        (_inlineScriptText != null && _inlineScriptText!.isNotEmpty);

    setState(() {
      _isProcessing = true;
      _livePercent = 0.02;
      _liveStep = isUrlMode
          ? '📥 جاري تنزيل ملف الفصل مباشرة من رابط Google Drive / السحابي...'
          : 'جاري رفع الملفات إلى السيرفر...';
      _liveDetail = isUrlMode ? chapterUrl : 'رفع ${_selectedImages.length} صفحات';
      _liveCurrentPage = 0;
      _liveTotalPages = isUrlMode ? 0 : _selectedImages.length;
      _livePhase = isUrlMode ? 'download' : 'upload';
    });

    _startLiveProgressPolling();

    try {
      final apiKey = await widget.apiService.getGeminiApiKey();

      final batchResponse = await widget.apiService.processBatch(
        imageFiles: isUrlMode ? null : _selectedImages,
        chapterUrl: isUrlMode ? chapterUrl : null,
        scriptFile: hasScript ? _selectedScriptFile : null,
        scriptText: hasScript ? _inlineScriptText : null,
        geminiApiKey: apiKey.isNotEmpty ? apiKey : null,
        fastMode: _fastMode,
        cleanImages: _cleanImages,
        openPcGui: _openPcGui,
        snapToBubbles: _snapToBubbles,
        onLiveProgress: _handleLiveProgressUpdate,
        onProgress: (sent, total) {
          if (total > 0 && sent < total && !isUrlMode) {
            setState(() {
              final upRatio = (sent / total) * 0.08;
              if (upRatio > _livePercent) _livePercent = upRatio;
              _liveStep = 'جاري رفع الصور إلى السيرفر...';
              _liveDetail =
                  '${(sent / 1024 / 1024).toStringAsFixed(1)} MB من ${(total / 1024 / 1024).toStringAsFixed(1)} MB (${((sent / total) * 100).toInt()}%)';
            });
          }
        },
      );

      _stopLiveProgressPolling();

      setState(() {
        _isProcessing = false;
        _livePercent = 1.0;
      });

      if (mounted) {
        _showSnack('🎉 اكتملت المعالجة بنجاح!');
        Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ReviewScreen(
              batchResponse: batchResponse,
              apiService: widget.apiService,
            ),
          ),
        );
      }
    } catch (e) {
      _stopLiveProgressPolling();
      setState(() => _isProcessing = false);
      _showSnack('حدث خطأ أثناء المعالجة: $e', isError: true);
    }
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: isError ? AppTheme.accentRose : AppTheme.accentEmerald,
      ),
    );
  }

  String _formatElapsed(int seconds) {
    final m = seconds ~/ 60;
    final s = seconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  Widget _buildConnectionBadge(bool isOnline) {
    if (!isOnline) {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
        decoration: BoxDecoration(
          color: AppTheme.accentRose.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: AppTheme.accentRose, width: 1),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 7,
              height: 7,
              decoration: const BoxDecoration(
                color: AppTheme.accentRose,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 5),
            const Text(
              'غير متصل 🔴',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: AppTheme.accentRose,
              ),
            ),
          ],
        ),
      );
    }

    final String baseUrl = widget.apiService.baseUrl.toLowerCase();
    final bool isColab = _health?.isColab == true || baseUrl.contains('colab');
    final bool isLan = baseUrl.contains('192.168.') ||
        baseUrl.contains('127.0.0.1') ||
        baseUrl.contains('localhost');

    String label = 'كمبيوتر محلي 💻';
    Color badgeColor = AppTheme.primaryCyan;

    if (isColab) {
      label = 'كولاب Colab ⚡';
      badgeColor = const Color(0xFFC084FC); // Purple / Colab
    } else if (isLan) {
      label = 'واي فاي محلي 🏠';
      badgeColor = AppTheme.accentEmerald;
    } else if (baseUrl.contains('ngrok')) {
      label = 'كمبيوتر Ngrok 🌐';
      badgeColor = const Color(0xFF38BDF8);
    }

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: badgeColor.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: badgeColor.withValues(alpha: 0.6), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(
              color: badgeColor,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: badgeColor,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isOnline = _health?.isOnline == true;
    final hasScript = _selectedScriptFile != null ||
        (_inlineScriptText != null && _inlineScriptText!.isNotEmpty);

    return Scaffold(
      appBar: AppBar(
        title: const Text('SmartCleaner Mobile'),
        leading: IconButton(
          icon: const Icon(Icons.settings_rounded),
          tooltip: 'الإعدادات والمزامنة',
          onPressed: () async {
            await Navigator.push(
              context,
              MaterialPageRoute(
                builder: (_) => SettingsScreen(apiService: widget.apiService),
              ),
            );
            _checkServer();
          },
        ),
        actions: [
          // Connection Status Button
          GestureDetector(
            onTap: () async {
              await _checkServer();
              if (mounted) {
                _showSnack(
                  isOnline
                      ? 'تم تحديث الاتصال: ${_health?.serverName ?? 'السيرفر متصل'} ✅'
                      : 'السيرفر غير متصل، اضغط على الإعدادات لضبط الرابط ⚠️',
                  isError: !isOnline,
                );
              }
            },
            child: _buildConnectionBadge(isOnline),
          ),
        ],
      ),
      body: Directionality(
        textDirection: TextDirection.rtl,
        child: Stack(
          children: [
            ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // 1. Manga Content Card (Dual Mode: Local Images or Google Drive / Cloud URL)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Header Row
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.auto_stories_rounded,
                                    color: AppTheme.primaryCyan),
                                const SizedBox(width: 8),
                                const Text(
                                  'محتوى فصل المانجا',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: (_inputMode == 0
                                        ? _selectedImages.isNotEmpty
                                        : _chapterUrlController.text.trim().isNotEmpty)
                                    ? AppTheme.primaryCyan.withValues(alpha: 0.15)
                                    : AppTheme.cardDark,
                                borderRadius: BorderRadius.circular(10),
                              ),
                              child: Text(
                                _inputMode == 0
                                    ? '${_selectedImages.length} صور محددة'
                                    : (_chapterUrlController.text.trim().isNotEmpty
                                        ? 'رابط سحابي جاهز ⚡'
                                        : 'في انتظار الرابط 🔗'),
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: (_inputMode == 0
                                          ? _selectedImages.isNotEmpty
                                          : _chapterUrlController.text.trim().isNotEmpty)
                                      ? AppTheme.primaryCyan
                                      : const Color(0xFF94A3B8),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 14),

                        // Mode Switcher Tabs
                        Container(
                          padding: const EdgeInsets.all(4),
                          decoration: BoxDecoration(
                            color: const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                                color: AppTheme.borderDark, width: 1),
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: GestureDetector(
                                  onTap: () => setState(() => _inputMode = 0),
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    padding: const EdgeInsets.symmetric(
                                        vertical: 8, horizontal: 4),
                                    decoration: BoxDecoration(
                                      color: _inputMode == 0
                                          ? AppTheme.cardDark
                                          : Colors.transparent,
                                      borderRadius: BorderRadius.circular(8),
                                      border: _inputMode == 0
                                          ? Border.all(
                                              color: AppTheme.primaryCyan
                                                  .withValues(alpha: 0.5))
                                          : null,
                                    ),
                                    child: Row(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Icon(
                                          Icons.photo_library_rounded,
                                          size: 15,
                                          color: _inputMode == 0
                                              ? AppTheme.primaryCyan
                                              : const Color(0xFF94A3B8),
                                        ),
                                        const SizedBox(width: 5),
                                        Flexible(
                                          child: Text(
                                            'صور من الهاتف',
                                            overflow: TextOverflow.ellipsis,
                                            maxLines: 1,
                                            style: TextStyle(
                                              fontSize: 11.5,
                                              fontWeight: _inputMode == 0
                                                  ? FontWeight.bold
                                                  : FontWeight.normal,
                                              color: _inputMode == 0
                                                  ? Colors.white
                                                  : const Color(0xFF94A3B8),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                              Expanded(
                                child: GestureDetector(
                                  onTap: () => setState(() => _inputMode = 1),
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 200),
                                    padding: const EdgeInsets.symmetric(
                                        vertical: 8, horizontal: 4),
                                    decoration: BoxDecoration(
                                      color: _inputMode == 1
                                          ? AppTheme.cardDark
                                          : Colors.transparent,
                                      borderRadius: BorderRadius.circular(8),
                                      border: _inputMode == 1
                                          ? Border.all(
                                              color: AppTheme.accentEmerald
                                                  .withValues(alpha: 0.5))
                                          : null,
                                    ),
                                    child: Row(
                                      mainAxisAlignment:
                                          MainAxisAlignment.center,
                                      children: [
                                        Icon(
                                          Icons.cloud_download_rounded,
                                          size: 15,
                                          color: _inputMode == 1
                                              ? AppTheme.accentEmerald
                                              : const Color(0xFF94A3B8),
                                        ),
                                        const SizedBox(width: 5),
                                        Flexible(
                                          child: Text(
                                            'Google Drive / رابط',
                                            overflow: TextOverflow.ellipsis,
                                            maxLines: 1,
                                            style: TextStyle(
                                              fontSize: 11.5,
                                              fontWeight: _inputMode == 1
                                                  ? FontWeight.bold
                                                  : FontWeight.normal,
                                              color: _inputMode == 1
                                                  ? Colors.white
                                                  : const Color(0xFF94A3B8),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 14),

                        // Tab 0 Content: Pick Local Images
                        if (_inputMode == 0) ...[
                          Row(
                            children: [
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: _pickImages,
                                  icon: const Icon(
                                      Icons.add_photo_alternate_rounded),
                                  label: Text(_selectedImages.isEmpty
                                      ? 'اختيار صور الفصل 🖼️'
                                      : 'إضافة المزيد من الصور +'),
                                ),
                              ),
                              if (_selectedImages.isNotEmpty) ...[
                                const SizedBox(width: 8),
                                IconButton(
                                  tooltip: 'مسح جميع الصور',
                                  icon: const Icon(Icons.delete_outline_rounded,
                                      color: AppTheme.accentRose),
                                  onPressed: () =>
                                      setState(() => _selectedImages.clear()),
                                ),
                              ],
                            ],
                          ),
                          if (_selectedImages.isNotEmpty) ...[
                            const SizedBox(height: 12),
                            SizedBox(
                              height: 75,
                              child: ListView.builder(
                                scrollDirection: Axis.horizontal,
                                itemCount: _selectedImages.length,
                                itemBuilder: (ctx, idx) {
                                  final img = _selectedImages[idx];
                                  return Container(
                                    margin: const EdgeInsets.only(left: 8),
                                    width: 55,
                                    decoration: BoxDecoration(
                                      borderRadius: BorderRadius.circular(8),
                                      image: DecorationImage(
                                        image: FileImage(img),
                                        fit: BoxFit.cover,
                                      ),
                                      border: Border.all(
                                        color: AppTheme.primaryCyan
                                            .withValues(alpha: 0.5),
                                      ),
                                    ),
                                    child: Align(
                                      alignment: Alignment.bottomCenter,
                                      child: Container(
                                        width: double.infinity,
                                        color: Colors.black54,
                                        padding: const EdgeInsets.symmetric(
                                            vertical: 1),
                                        child: Text(
                                          '#${idx + 1}',
                                          textAlign: TextAlign.center,
                                          style: const TextStyle(
                                            fontSize: 9,
                                            color: Colors.white,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ),
                                    ),
                                  );
                                },
                              ),
                            ),
                          ],
                        ]

                        // Tab 1 Content: Google Drive / Cloud URL
                        else ...[
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              TextField(
                                controller: _chapterUrlController,
                                style: const TextStyle(fontSize: 13),
                                decoration: InputDecoration(
                                  hintText:
                                      'الصق رابط Google Drive أو أرشيف الفصل المباشر...',
                                  hintStyle: const TextStyle(
                                      fontSize: 12, color: Color(0xFF64748B)),
                                  prefixIcon: const Icon(
                                      Icons.cloud_download_rounded,
                                      color: AppTheme.primaryCyan),
                                  suffixIcon: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      if (_chapterUrlController.text
                                          .trim()
                                          .isNotEmpty)
                                        IconButton(
                                          icon: const Icon(Icons.clear_rounded,
                                              size: 18,
                                              color: Color(0xFF94A3B8)),
                                          onPressed: () => setState(() =>
                                              _chapterUrlController.clear()),
                                          tooltip: 'مسح الرابط',
                                        ),
                                      IconButton(
                                        icon: const Icon(
                                            Icons.content_paste_rounded,
                                            size: 19,
                                            color: AppTheme.primaryCyan),
                                        onPressed: _pasteFromClipboard,
                                        tooltip: 'لصق من الحافظة 📋',
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: 8),

                              // URL Detection Badge
                              if (_chapterUrlController.text.trim().isNotEmpty) ...[
                                Builder(
                                  builder: (context) {
                                    final info = _detectUrlInfo(
                                        _chapterUrlController.text);
                                    final Color badgeColor =
                                        info['color'] as Color;
                                    return Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 10, vertical: 6),
                                      decoration: BoxDecoration(
                                        color:
                                            badgeColor.withValues(alpha: 0.12),
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(
                                            color: badgeColor
                                                .withValues(alpha: 0.35)),
                                      ),
                                      child: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(info['icon'] as IconData,
                                              size: 15, color: badgeColor),
                                          const SizedBox(width: 6),
                                          Text(
                                            info['label'] as String,
                                            style: TextStyle(
                                              fontSize: 11,
                                              fontWeight: FontWeight.bold,
                                              color: badgeColor,
                                            ),
                                          ),
                                        ],
                                      ),
                                    );
                                  },
                                ),
                                const SizedBox(height: 8),
                              ],

                              // Info & Help Box
                              Container(
                                width: double.infinity,
                                padding: const EdgeInsets.all(10),
                                decoration: BoxDecoration(
                                  color: const Color(0xFF0F172A),
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                      color: AppTheme.borderDark, width: 1),
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: const [
                                    Row(
                                      children: [
                                        Icon(Icons.bolt_rounded,
                                            size: 14,
                                            color: AppTheme.primaryCyan),
                                        SizedBox(width: 5),
                                        Text(
                                          'سرعة جيجابت فائقة وتوفير للبيانات:',
                                          style: TextStyle(
                                            fontSize: 11,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.white,
                                          ),
                                        ),
                                      ],
                                    ),
                                    SizedBox(height: 4),
                                    Text(
                                      '• يقوم السيرفر بتنزيل الفصل خلال ثوانٍ معدودة دون استهلاك باقة هاتفك.\n• يدعم مجلدات Google Drive، والملفات الفردية، وأرشيفات (.zip / .rar / .cbz).\n• تأكد أن إذن مشاركة الرابط هو: "Anyone with the link" (أي شخص لديه الرابط).',
                                      style: TextStyle(
                                        fontSize: 10.5,
                                        color: Color(0xFF94A3B8),
                                        height: 1.45,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // 2. Translation Script Card (Clearly marked Optional)
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.translate_rounded,
                                    color: AppTheme.primaryBlue),
                                const SizedBox(width: 8),
                                const Text(
                                  'ملف أو نص الترجمة',
                                  style: TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 8, vertical: 2),
                              decoration: BoxDecoration(
                                color: hasScript
                                    ? AppTheme.accentEmerald
                                        .withValues(alpha: 0.15)
                                    : const Color(0xFF334155),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Text(
                                hasScript ? 'ترجمة مفعّلة ⚡' : '(اختياري)',
                                style: TextStyle(
                                  fontSize: 11,
                                  fontWeight: FontWeight.bold,
                                  color: hasScript
                                      ? AppTheme.accentEmerald
                                      : const Color(0xFF94A3B8),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        Text(
                          hasScript
                              ? 'سيتم استخراج الفقاعات ومطابقتها مع الترجمة وتوليد ملفات TypeR JSON.'
                              : 'اتركه فارغاً إذا كنت تريد فقط تنظيف وتبييض الصفحات 🧹',
                          style: const TextStyle(
                            fontSize: 11,
                            color: Color(0xFF94A3B8),
                          ),
                        ),
                        const SizedBox(height: 14),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: _pickScriptFile,
                                icon: const Icon(Icons.upload_file_rounded),
                                label: Text(
                                  _selectedScriptFile != null
                                      ? _selectedScriptFile!.path
                                          .split(Platform.pathSeparator)
                                          .last
                                      : 'رفع ملف نصي (.txt)',
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            IconButton(
                              tooltip: 'لصق أو كتابة النص يدوياً',
                              icon: const Icon(Icons.edit_note_rounded,
                                  color: AppTheme.primaryCyan),
                              onPressed: _openInlineScriptDialog,
                            ),
                            if (hasScript) ...[
                              const SizedBox(width: 4),
                              IconButton(
                                tooltip: 'إلغاء الترجمة',
                                icon: const Icon(Icons.close_rounded,
                                    color: AppTheme.accentRose),
                                onPressed: () {
                                  setState(() {
                                    _selectedScriptFile = null;
                                    _inlineScriptText = null;
                                  });
                                },
                              ),
                            ],
                          ],
                        ),
                        if (hasScript) ...[
                          const SizedBox(height: 10),
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: AppTheme.accentEmerald
                                  .withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(
                                  color: AppTheme.accentEmerald
                                      .withValues(alpha: 0.3)),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.check_circle_outline_rounded,
                                    color: AppTheme.accentEmerald, size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _selectedScriptFile != null
                                        ? 'تم اختيار الملف: ${_selectedScriptFile!.path.split(Platform.pathSeparator).last}'
                                        : 'تم تعيين سكريبت يدوي (${_inlineScriptText!.split('\n').length} أسطر)',
                                    style: const TextStyle(
                                      fontSize: 12,
                                      fontWeight: FontWeight.bold,
                                      color: AppTheme.accentEmerald,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),

                // 3. Processing Options Card
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'خيارات المعالجة والتنظيف',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 8),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('تبييض وتنظيف الصفحات بـ AI'),
                          subtitle: const Text(
                            'مسح النصوص الأصلية وإعادة رسم الخلفيات باستخدام IOPaint',
                            style: TextStyle(fontSize: 11),
                          ),
                          value: _cleanImages,
                          onChanged: (val) {
                            setState(() => _cleanImages = val);
                            _syncOptionToPc('iopaint_enabled', val);
                          },
                        ),
                        const Divider(height: 1),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('الوضع السريع (تخطي OCR)'),
                          subtitle: const Text(
                            'تسريع المعالجة بتخطي التعرف على النص الياباني',
                            style: TextStyle(fontSize: 11),
                          ),
                          value: _fastMode,
                          onChanged: (val) {
                            setState(() => _fastMode = val);
                            _syncOptionToPc('fast_mode', val);
                          },
                        ),
                        const Divider(height: 1),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('مطابقة أبعاد الفقاعات الدقيقة'),
                          subtitle: const Text(
                            'ضبط المربعات لتشمل كامل انحناءات الفقاعة بدقة',
                            style: TextStyle(fontSize: 11),
                          ),
                          value: _snapToBubbles,
                          onChanged: (val) {
                            setState(() => _snapToBubbles = val);
                            _syncOptionToPc('snap_to_bubbles', val);
                          },
                        ),
                        const Divider(height: 1),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('فتح المشروع تلقائياً على الكمبيوتر'),
                          subtitle: const Text(
                            'فتح واجهة SmartCleaner-AI على شاشة الكمبيوتر فور انتهاء المعالجة',
                            style: TextStyle(fontSize: 11),
                          ),
                          value: _openPcGui,
                          onChanged: (val) => setState(() => _openPcGui = val),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 90),
              ],
            ),

            // 4. Ultra-Detailed Live Progress Modal Overlay
            if (_isProcessing)
              Container(
                color: Colors.black87,
                width: double.infinity,
                height: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Center(
                  child: Card(
                    color: const Color(0xFF1E293B),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(20),
                      side: const BorderSide(
                          color: AppTheme.primaryCyan, width: 1.5),
                    ),
                    elevation: 16,
                    child: Padding(
                      padding: const EdgeInsets.all(22),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Header Row (Status & Timer)
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Row(
                                children: [
                                  const Icon(Icons.memory_rounded,
                                      color: AppTheme.primaryCyan, size: 22),
                                  const SizedBox(width: 8),
                                  const Text(
                                    'جاري المعالجة على الكمبيوتر...',
                                    style: TextStyle(
                                      fontSize: 15,
                                      fontWeight: FontWeight.bold,
                                      color: Colors.white,
                                    ),
                                  ),
                                ],
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 8, vertical: 3),
                                decoration: BoxDecoration(
                                  color: Colors.black45,
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(
                                      color: const Color(0xFF475569)),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(Icons.timer_outlined,
                                        size: 13,
                                        color: AppTheme.primaryCyan),
                                    const SizedBox(width: 4),
                                    Text(
                                      _formatElapsed(_elapsedSeconds),
                                      style: const TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.bold,
                                        color: AppTheme.primaryCyan,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 18),

                          // Large Percentage Text
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                _liveCurrentPage > 0
                                    ? 'صفحة $_liveCurrentPage من $_liveTotalPages'
                                    : 'بدء المهام...',
                                style: const TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.bold,
                                  color: AppTheme.accentEmerald,
                                ),
                              ),
                              Text(
                                '${(_livePercent * 100).toInt()}%',
                                style: const TextStyle(
                                  fontSize: 26,
                                  fontWeight: FontWeight.bold,
                                  color: AppTheme.primaryCyan,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),

                          // Linear Progress Bar
                          ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: LinearProgressIndicator(
                              value: _livePercent,
                              minHeight: 8,
                              color: AppTheme.primaryCyan,
                              backgroundColor: const Color(0xFF0F172A),
                            ),
                          ),
                          const SizedBox(height: 16),

                          // Current Step Title Box
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(0xFF0F172A),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                  color: AppTheme.borderDark, width: 1),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  _liveStep,
                                  style: const TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                                if (_liveDetail.isNotEmpty) ...[
                                  const SizedBox(height: 4),
                                  Text(
                                    _liveDetail,
                                    style: const TextStyle(
                                      fontSize: 11,
                                      color: Color(0xFF94A3B8),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                          const SizedBox(height: 16),

                          // Stages Mini Timeline
                          _buildStageItem(
                            title: '1. رفع الصور والملفات',
                            isActive: _livePhase == 'upload',
                            isDone: _livePercent > 0.10,
                            icon: Icons.cloud_upload_rounded,
                          ),
                          _buildStageItem(
                            title: '2. كشف الفقاعات واستخراج النصوص (OCR)',
                            isActive: _livePhase == 'ocr',
                            isDone: _livePercent > 0.40,
                            icon: Icons.document_scanner_rounded,
                          ),
                          _buildStageItem(
                            title: '3. تبييض وتنظيف بالذكاء الاصطناعي (IOPaint)',
                            isActive: _livePhase == 'cleaning',
                            isDone: _livePercent > 0.80,
                            icon: Icons.auto_fix_high_rounded,
                          ),
                          if (hasScript)
                            _buildStageItem(
                              title: '4. مطابقة الترجمة الذكية (Gemini AI)',
                              isActive: _livePhase == 'translate',
                              isDone: _livePercent > 0.90,
                              icon: Icons.translate_rounded,
                            ),
                          _buildStageItem(
                            title: '5. حفظ وتجهيز حزم النتائج',
                            isActive: _livePhase == 'packaging' ||
                                _livePhase == 'done',
                            isDone: _livePercent >= 1.0,
                            icon: Icons.save_alt_rounded,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
      bottomSheet: Container(
        padding: const EdgeInsets.all(16),
        color: AppTheme.surfaceDark,
        child: SizedBox(
          width: double.infinity,
          height: 54,
          child: ElevatedButton.icon(
            onPressed: (_isProcessing ||
                    !isOnline ||
                    (_inputMode == 0 && _selectedImages.isEmpty) ||
                    (_inputMode == 1 && _chapterUrlController.text.trim().isEmpty))
                ? null
                : _startProcessing,
            style: ElevatedButton.styleFrom(
              backgroundColor: hasScript
                  ? AppTheme.primaryCyan
                  : AppTheme.accentEmerald,
              foregroundColor: Colors.black,
              disabledBackgroundColor: const Color(0xFF334155),
            ),
            icon: Icon(
              hasScript
                  ? Icons.rocket_launch_rounded
                  : (_inputMode == 1
                      ? Icons.cloud_download_rounded
                      : Icons.cleaning_services_rounded),
            ),
            label: Text(
              _getActionButtonText(isOnline, hasScript),
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStageItem({
    required String title,
    required bool isActive,
    required bool isDone,
    required IconData icon,
  }) {
    Color iconColor = const Color(0xFF475569);
    Color textColor = const Color(0xFF64748B);

    if (isDone) {
      iconColor = AppTheme.accentEmerald;
      textColor = const Color(0xFFCBD5E1);
    } else if (isActive) {
      iconColor = AppTheme.primaryCyan;
      textColor = AppTheme.primaryCyan;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          if (isActive)
            const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(
                strokeWidth: 2,
                color: AppTheme.primaryCyan,
              ),
            )
          else if (isDone)
            const Icon(Icons.check_circle_rounded,
                size: 14, color: AppTheme.accentEmerald)
          else
            Icon(icon, size: 14, color: iconColor),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isActive ? FontWeight.bold : FontWeight.normal,
                color: textColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _getActionButtonText(bool isOnline, bool hasScript) {
    if (!isOnline) return 'السيرفر غير متصل - تحقق من السيرفر ⚠️';

    if (_inputMode == 1) {
      final url = _chapterUrlController.text.trim();
      if (url.isEmpty) return 'الصق رابط Google Drive للبدء 🔗';
      if (hasScript) {
        return 'بدء التنزيل واستخراج الترجمة (Google Drive) ⚡';
      }
      return 'بدء تنزيل وتبييض الفصل (Google Drive) ✨';
    }

    if (_selectedImages.isEmpty) return 'اختر صور المانجا للبدء 🖼️';

    if (hasScript) {
      return 'بدء الاستخراج ومطابقة الترجمة (${_selectedImages.length} صفحات) 🚀';
    }
    return 'بدء تنظيف وتبييض الصفحات (${_selectedImages.length} صفحات) ✨';
  }
}
