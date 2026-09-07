double _safeDouble(dynamic val, [double defaultVal = 0.0]) {
  if (val == null) return defaultVal;
  if (val is num) return val.toDouble();
  if (val is String) return double.tryParse(val) ?? defaultVal;
  return defaultVal;
}

int _safeInt(dynamic val, [int defaultVal = 0]) {
  if (val == null) return defaultVal;
  if (val is int) return val;
  if (val is num) return val.toInt();
  if (val is String) return int.tryParse(val) ?? defaultVal;
  return defaultVal;
}

class BubbleItem {
  final int id;
  final List<double> bounds; // [x, y, w, h]
  final String originalText;
  String assignedTranslation;
  final double confidence;
  final int readingOrder;

  BubbleItem({
    required this.id,
    required this.bounds,
    required this.originalText,
    required this.assignedTranslation,
    this.confidence = 1.0,
    this.readingOrder = 1,
  });

  factory BubbleItem.fromJson(Map<String, dynamic> json, int defaultId) {
    List<double> parsedBounds = [0, 0, 0, 0];

    if (json['bounds'] is List && (json['bounds'] as List).isNotEmpty) {
      final list = json['bounds'] as List;
      parsedBounds = [
        list.isNotEmpty ? _safeDouble(list[0]) : 0.0,
        list.length > 1 ? _safeDouble(list[1]) : 0.0,
        list.length > 2 ? _safeDouble(list[2]) : 0.0,
        list.length > 3 ? _safeDouble(list[3]) : 0.0,
      ];
    } else {
      final x = _safeDouble(json['x'] ?? json['left']);
      final y = _safeDouble(json['y'] ?? json['top']);
      final w = _safeDouble(json['width'] ?? json['w']);
      final h = _safeDouble(json['height'] ?? json['h']);
      parsedBounds = [x, y, w, h];
    }

    int parsedId = defaultId;
    if (json['id'] is int) {
      parsedId = json['id'];
    } else if (json['id'] is String) {
      final digits = (json['id'] as String).replaceAll(RegExp(r'\D'), '');
      parsedId = int.tryParse(digits) ?? defaultId;
    } else if (json['index'] is num) {
      parsedId = (json['index'] as num).toInt() + 1;
    }

    return BubbleItem(
      id: parsedId,
      bounds: parsedBounds,
      originalText: json['text']?.toString() ?? json['original_text']?.toString() ?? '',
      assignedTranslation: json['assigned_translation']?.toString() ??
          json['translation']?.toString() ??
          json['text']?.toString() ??
          '',
      confidence: _safeDouble(json['confidence'], 1.0),
      readingOrder: _safeInt(json['reading_order'], 1),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'bounds': bounds,
      'text': originalText,
      'assigned_translation': assignedTranslation,
      'translation': assignedTranslation,
      'confidence': confidence,
      'reading_order': readingOrder,
    };
  }
}

class PageResult {
  final String imagePath;
  final String imageName;
  final String imageUrl;
  final String? cleanedUrl;
  final int bubblesCount;
  final double width;
  final double height;
  final List<BubbleItem> bubbles;

  PageResult({
    required this.imagePath,
    required this.imageName,
    required this.imageUrl,
    this.cleanedUrl,
    required this.bubblesCount,
    this.width = 1000.0,
    this.height = 1500.0,
    required this.bubbles,
  });

  factory PageResult.fromJson(Map<String, dynamic> json, String baseUrl) {
    final rawImgUrl = json['image_url']?.toString() ?? '';
    final rawCleanUrl = json['cleaned_url']?.toString();

    String fullImgUrl = rawImgUrl;
    if (rawImgUrl.startsWith('/')) {
      fullImgUrl = '$baseUrl$rawImgUrl';
    }

    String? fullCleanUrl;
    if (rawCleanUrl != null && rawCleanUrl.isNotEmpty) {
      fullCleanUrl = rawCleanUrl.startsWith('/')
          ? '$baseUrl$rawCleanUrl'
          : rawCleanUrl;
    }

    final rawBubbles = (json['bubbles'] as List? ?? []);
    final parsedBubbles = <BubbleItem>[];
    for (int i = 0; i < rawBubbles.length; i++) {
      if (rawBubbles[i] is Map<String, dynamic>) {
        parsedBubbles.add(
            BubbleItem.fromJson(rawBubbles[i] as Map<String, dynamic>, i + 1));
      }
    }

    return PageResult(
      imagePath: json['image_path']?.toString() ?? '',
      imageName: json['image_name']?.toString() ?? 'Page',
      imageUrl: fullImgUrl,
      cleanedUrl: fullCleanUrl,
      bubblesCount: _safeInt(json['bubbles_count'], parsedBubbles.length),
      width: _safeDouble(json['width'], 1000.0),
      height: _safeDouble(json['height'], 1500.0),
      bubbles: parsedBubbles,
    );
  }
}

class DownloadsInfo {
  final String? jsonZip;
  final String? cleanedZip;
  final String? projectFtr;

  DownloadsInfo({
    this.jsonZip,
    this.cleanedZip,
    this.projectFtr,
  });

  factory DownloadsInfo.fromJson(Map<String, dynamic> json, String baseUrl) {
    String? fullUrl(dynamic u) {
      if (u == null) return null;
      final s = u.toString();
      if (s.isEmpty) return null;
      return s.startsWith('/') ? '$baseUrl$s' : s;
    }

    return DownloadsInfo(
      jsonZip: fullUrl(json['json_zip']),
      cleanedZip: fullUrl(json['cleaned_zip']),
      projectFtr: fullUrl(json['project_ftr']),
    );
  }
}

class BatchResponse {
  final bool success;
  final String batchId;
  final int pagesCount;
  final List<PageResult> pages;
  final DownloadsInfo downloads;

  BatchResponse({
    required this.success,
    required this.batchId,
    required this.pagesCount,
    required this.pages,
    required this.downloads,
  });

  factory BatchResponse.fromJson(Map<String, dynamic> json, String baseUrl) {
    final rawPages = (json['pages'] as List? ?? []);
    final parsedPages = rawPages
        .whereType<Map<String, dynamic>>()
        .map((p) => PageResult.fromJson(p, baseUrl))
        .toList();

    return BatchResponse(
      success: json['success'] == true,
      batchId: json['batch_id']?.toString() ?? '',
      pagesCount: _safeInt(json['pages_count'], parsedPages.length),
      pages: parsedPages,
      downloads: DownloadsInfo.fromJson(
        json['downloads'] as Map<String, dynamic>? ?? {},
        baseUrl,
      ),
    );
  }
}

class ServerHealth {
  final bool isOnline;
  final String serverName;
  final String serverType; // 'pc' or 'colab'
  final bool isColab;
  final String version;
  final bool iopaintOnline;
  final String iopaintModel;
  final String iopaintUrl;
  final bool geminiConfigured;

  ServerHealth({
    required this.isOnline,
    required this.serverName,
    this.serverType = 'pc',
    this.isColab = false,
    required this.version,
    required this.iopaintOnline,
    required this.iopaintModel,
    required this.iopaintUrl,
    required this.geminiConfigured,
  });

  factory ServerHealth.fromJson(Map<String, dynamic> json) {
    final iopaint = json['iopaint'] as Map<String, dynamic>? ?? {};
    final String server = json['server']?.toString() ?? 'FastTypeR PC Server';
    final bool colab = json['is_colab'] == true ||
        json['server_type'] == 'colab' ||
        server.toLowerCase().contains('colab');

    return ServerHealth(
      isOnline: json['status'] == 'online',
      serverName: server,
      serverType: json['server_type']?.toString() ?? (colab ? 'colab' : 'pc'),
      isColab: colab,
      version: json['version']?.toString() ?? '1.0.0',
      iopaintOnline: iopaint['online'] == true,
      iopaintModel: iopaint['model']?.toString() ?? 'None',
      iopaintUrl: iopaint['url']?.toString() ?? '',
      geminiConfigured: json['gemini_configured'] == true,
    );
  }

  factory ServerHealth.offline() {
    return ServerHealth(
      isOnline: false,
      serverName: 'Offline',
      serverType: 'offline',
      isColab: false,
      version: '0.0.0',
      iopaintOnline: false,
      iopaintModel: 'None',
      iopaintUrl: '',
      geminiConfigured: false,
    );
  }
}
