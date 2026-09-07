import 'dart:io';
import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/batch_model.dart';

class ApiService {
  static const String defaultNgrokUrl = 'http://10.0.2.2:8000';
  static const String prefUrlKey = 'smartcleaner_server_url';
  static const String prefApiKey = 'smartcleaner_gemini_api_key';

  late Dio _dio;
  String _baseUrl = defaultNgrokUrl;

  ApiService() {
    _initDio();
  }

  void _initDio() {
    _dio = Dio(
      BaseOptions(
        baseUrl: _baseUrl,
        connectTimeout: const Duration(seconds: 45),
        receiveTimeout: const Duration(minutes: 5),
        sendTimeout: const Duration(minutes: 5),
        validateStatus: (status) => status != null && status < 500,
        headers: {
          'ngrok-skip-browser-warning': 'true',
          'User-Agent': 'SmartCleaner-Mobile/1.0',
        },
      ),
    );
  }

  String get baseUrl => _baseUrl;

  Future<void> loadSavedConfig() async {
    final prefs = await SharedPreferences.getInstance();
    final savedUrl = prefs.getString(prefUrlKey);
    if (savedUrl != null && savedUrl.trim().isNotEmpty) {
      _baseUrl = savedUrl.trim().replaceAll(RegExp(r'/+$'), '');
      _initDio();
    }
  }

  Future<void> updateBaseUrl(String newUrl) async {
    _baseUrl = newUrl.trim().replaceAll(RegExp(r'/+$'), '');
    _initDio();
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(prefUrlKey, _baseUrl);
  }

  Future<Map<String, dynamic>?> fetchPcConfig() async {
    try {
      final response = await _dio.get('/api/config');
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data['config'] as Map<String, dynamic>?;
      }
      return null;
    } catch (e) {
      return null;
    }
  }

  Future<Map<String, dynamic>> savePcConfig(Map<String, dynamic> config) async {
    try {
      final response = await _dio.post('/api/config', data: config);
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data;
      }
      return {'success': false, 'message': 'Failed to save config to PC'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<String> getGeminiApiKey() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(prefApiKey) ?? '';
  }

  Future<void> saveGeminiApiKey(String key) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(prefApiKey, key.trim());
  }

  Future<ServerHealth> checkHealth() async {
    try {
      final response = await _dio.get('/api/health');
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return ServerHealth.fromJson(response.data);
      }
      return ServerHealth.offline();
    } catch (e) {
      return ServerHealth.offline();
    }
  }

  Future<Map<String, dynamic>> startIOPaint() async {
    try {
      final response = await _dio.post('/api/iopaint/start');
      return response.data is Map<String, dynamic>
          ? response.data
          : {'success': false, 'message': 'Unknown response'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<Map<String, dynamic>> stopIOPaint() async {
    try {
      final response = await _dio.post('/api/iopaint/stop');
      return response.data is Map<String, dynamic>
          ? response.data
          : {'success': false, 'message': 'Unknown response'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<Map<String, dynamic>> launchPcGui({String? projectPath}) async {
    try {
      final Map<String, dynamic> dataMap = {};
      if (projectPath != null) {
        dataMap['project_path'] = projectPath;
      }
      final formData = FormData.fromMap(dataMap);
      final response = await _dio.post('/api/gui/launch', data: formData);
      return response.data is Map<String, dynamic>
          ? response.data
          : {'success': true, 'message': 'تم إرسال أمر فتح البرنامج'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<Map<String, dynamic>> closePcGui() async {
    try {
      final response = await _dio.post('/api/gui/close');
      return response.data is Map<String, dynamic>
          ? response.data
          : {'success': true, 'message': 'تم إرسال أمر إغلاق البرنامج'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<Map<String, dynamic>> shutdownServer() async {
    try {
      final response = await _dio.post('/api/server/shutdown');
      return response.data is Map<String, dynamic>
          ? response.data
          : {'success': true, 'message': 'تم إغلاق الخادم بنجاح'};
    } catch (e) {
      return {'success': true, 'message': 'تم إرسال أمر الإغلاق'};
    }
  }

  Future<Map<String, dynamic>> triggerPcGui({String? projectPath}) async {
    return launchPcGui(projectPath: projectPath);
  }

  Future<Map<String, dynamic>> pingServer() async {
    final stopwatch = Stopwatch()..start();
    try {
      final response = await _dio.get('/api/health');
      stopwatch.stop();
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return {
          'online': true,
          'latencyMs': stopwatch.elapsedMilliseconds,
          'health': ServerHealth.fromJson(response.data),
        };
      }
      return {
        'online': false,
        'latencyMs': -1,
        'health': ServerHealth.offline(),
      };
    } catch (e) {
      stopwatch.stop();
      return {
        'online': false,
        'latencyMs': -1,
        'health': ServerHealth.offline(),
        'error': e.toString(),
      };
    }
  }

  Future<BatchResponse> processBatch({
    List<File>? imageFiles,
    String? chapterUrl,
    File? scriptFile,
    String? scriptText,
    String? geminiApiKey,
    bool fastMode = true,
    bool cleanImages = false,
    bool openPcGui = false,
    bool snapToBubbles = true,
    String iopaintModel = 'anime-lama',
    bool iopaintAdaptive = true,
    int iopaintDilation = 5,
    Function(int sent, int total)? onProgress,
    Function(Map<String, dynamic> prog)? onLiveProgress,
  }) async {
    final bool hasImages = imageFiles != null && imageFiles.isNotEmpty;
    final bool hasUrl = chapterUrl != null && chapterUrl.trim().isNotEmpty;

    if (!hasImages && !hasUrl) {
      throw Exception('يرجى اختيار صور المانجا أو إدخال رابط الفصل / Google Drive أولاً.');
    }

    final Map<String, dynamic> formMap = {
      'fast_mode': fastMode.toString(),
      'clean_images': cleanImages.toString(),
      'open_pc_gui': openPcGui.toString(),
      'snap_to_bubbles': snapToBubbles.toString(),
      'iopaint_model': iopaintModel,
      'iopaint_adaptive': iopaintAdaptive.toString(),
      'iopaint_dilation': iopaintDilation.toString(),
      'async_mode': 'true',
    };

    if (hasUrl) {
      formMap['chapter_url'] = chapterUrl.trim();
    }

    if (geminiApiKey != null && geminiApiKey.isNotEmpty) {
      formMap['gemini_api_key'] = geminiApiKey.trim();
    }

    if (scriptText != null && scriptText.isNotEmpty) {
      formMap['script_text'] = scriptText;
    }

    if (scriptFile != null) {
      formMap['script_file'] = await MultipartFile.fromFile(
        scriptFile.path,
        filename: scriptFile.path.split(Platform.pathSeparator).last,
      );
    }

    if (hasImages) {
      final List<MultipartFile> imageUploads = [];
      for (final img in imageFiles) {
        imageUploads.add(
          await MultipartFile.fromFile(
            img.path,
            filename: img.path.split(Platform.pathSeparator).last,
          ),
        );
      }
      formMap['images'] = imageUploads;
    }

    final formData = FormData.fromMap(formMap);

    // 1. Initiate processing on server
    final response = await _dio.post(
      '/api/process',
      data: formData,
      onSendProgress: onProgress,
    );

    if (response.statusCode != 200 || response.data is! Map<String, dynamic>) {
      throw Exception('استجاب السيرفر برمز غير متوقع: ${response.statusCode}');
    }

    final initData = response.data as Map<String, dynamic>;
    final String batchId = initData['batch_id']?.toString() ?? '';

    if (batchId.isEmpty) {
      throw Exception('لم يتم استلام معرف المعالجة (batch_id) من السيرفر.');
    }

    // 2. Poll for background progress until done
    final startTime = DateTime.now();
    const maxDuration = Duration(minutes: 25);

    while (DateTime.now().difference(startTime) < maxDuration) {
      await Future.delayed(const Duration(milliseconds: 450));

      final prog = await getLatestProgress(batchId: batchId);
      onLiveProgress?.call(prog);

      final phase = prog['phase']?.toString() ?? '';

      if (phase == 'done' || prog['result'] != null) {
        Map<String, dynamic>? resData;
        if (prog['result'] is Map<String, dynamic>) {
          resData = prog['result'] as Map<String, dynamic>;
        } else {
          resData = await fetchBatchResult(batchId);
        }

        if (resData != null) {
          return BatchResponse.fromJson(resData, _baseUrl);
        }
      } else if (phase == 'error') {
        final err = prog['error'] ?? prog['detail'] ?? 'حدث خطأ أثناء معالجة الفصل على السيرفر';
        throw Exception(err.toString());
      }
    }

    throw Exception('استغرقت المعالجة وقتاً أطول من المتوقع على السيرفر.');
  }

  Future<Map<String, dynamic>?> fetchBatchResult(String batchId) async {
    try {
      final response = await _dio.get('/api/batch/$batchId/result');
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
    } catch (_) {}
    return null;
  }

  Future<bool> updateBubbleTranslation({
    required String batchId,
    required String pageKey,
    required int bubbleIndex,
    required String arabicText,
  }) async {
    try {
      final formData = FormData.fromMap({
        'page_key': pageKey,
        'bubble_index': bubbleIndex,
        'arabic_text': arabicText,
      });

      final response = await _dio.post(
        '/api/batch/$batchId/update-bubble',
        data: formData,
      );

      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }

  Future<Map<String, dynamic>> executeBubbleCleaningAction({
    required String batchId,
    required String pageKey,
    required int bubbleIndex,
    required String action, // "reclean_ai", "restore_original", "flat_white"
    int dilation = 5,
  }) async {
    try {
      final formData = FormData.fromMap({
        'page_key': pageKey,
        'bubble_index': bubbleIndex,
        'action': action,
        'dilation': dilation,
      });

      final response = await _dio.post(
        '/api/batch/$batchId/bubble-cleaning-action',
        data: formData,
      );

      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        final data = response.data as Map<String, dynamic>;
        String? cleanUrl = data['cleaned_url']?.toString();
        if (cleanUrl != null && cleanUrl.startsWith('/')) {
          cleanUrl = '$_baseUrl$cleanUrl';
        }
        return {
          'success': data['success'] == true,
          'message': data['message'] ?? 'تم تنفيذ العملية',
          'cleaned_url': cleanUrl,
        };
      }
      return {'success': false, 'message': 'فشل الاتصال بالسيرفر'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }

  Future<Map<String, dynamic>> getLatestProgress({String? batchId}) async {
    try {
      final endpoint = batchId != null && batchId.isNotEmpty
          ? '/api/progress/$batchId'
          : '/api/progress-latest';

      final response = await _dio.get(endpoint);
      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
    } catch (_) {}
    return {
      'percent': 0.0,
      'step': 'جاري المعالجة...',
      'detail': '',
      'phase': 'idle',
      'current_page': 0,
      'total_pages': 0
    };
  }

  Future<Map<String, dynamic>> saveBatchToPc({
    required String batchId,
    required String folderName,
    String format = 'original',
    bool saveCleaned = true,
    bool saveRaw = false,
    bool saveJson = true,
    String? customPcDir,
  }) async {
    try {
      final formData = FormData.fromMap({
        'folder_name': folderName,
        'format': format,
        'save_cleaned': saveCleaned,
        'save_raw': saveRaw,
        'save_json': saveJson,
        if (customPcDir != null && customPcDir.isNotEmpty)
          'custom_pc_dir': customPcDir,
      });

      final response = await _dio.post(
        '/api/batch/$batchId/save-to-pc',
        data: formData,
      );

      if (response.statusCode == 200 && response.data is Map<String, dynamic>) {
        return response.data as Map<String, dynamic>;
      }
      return {'success': false, 'message': 'فشل حفظ الملفات على الكمبيوتر'};
    } catch (e) {
      return {'success': false, 'message': e.toString()};
    }
  }
}
