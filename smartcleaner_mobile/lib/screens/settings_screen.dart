import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/api_service.dart';
import '../models/batch_model.dart';
import '../theme/app_theme.dart';

class SettingsScreen extends StatefulWidget {
  final ApiService apiService;

  const SettingsScreen({super.key, required this.apiService});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;

  // Controllers
  late TextEditingController _urlController;
  late TextEditingController _keyController;
  late TextEditingController _iopaintUrlController;

  // Options matching PC GUI
  bool _fastMode = false;
  bool _snapToBubbles = true;
  int _maskPadding = 5;
  bool _iopaintEnabled = true;
  bool _iopaintAdaptive = true;
  String _iopaintModel = 'anime-lama';
  int _iopaintDilation = 5;

  final List<String> _iopaintModels = [
    'anime-lama',
    'lama',
    'manga',
    'ldm',
    'zits',
    'mat',
    'fcf',
    'migan',
    'cv2'
  ];

  bool _obscureApiKey = true;
  bool _isLoadingConfig = false;
  bool _isSavingConfig = false;
  ServerHealth? _health;
  int? _pingLatency;

  // Server Category Selection (0 = PC Local/Ngrok, 1 = Colab Cloud GPU)
  int _serverCategory = 0;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
    _urlController = TextEditingController(text: widget.apiService.baseUrl);
    _keyController = TextEditingController();
    _iopaintUrlController = TextEditingController(text: 'http://127.0.0.1:8080');

    // Auto-detect server category from existing URL
    final currentUrl = widget.apiService.baseUrl.toLowerCase();
    if (currentUrl.contains('colab') || currentUrl.contains('ngrok')) {
      _serverCategory = currentUrl.contains('192.168.') || currentUrl.contains('127.0.0.1') ? 0 : 1;
    }

    _loadAndSyncFromPc();
  }

  Future<void> _pasteServerUrl() async {
    try {
      final data = await Clipboard.getData(Clipboard.kTextPlain);
      if (data != null && data.text != null && data.text!.trim().isNotEmpty) {
        setState(() {
          _urlController.text = data.text!.trim();
        });
        _saveAndSyncToPc();
      }
    } catch (_) {}
  }

  Future<void> _loadAndSyncFromPc() async {
    if (!mounted) return;
    setState(() => _isLoadingConfig = true);

    // 1. Check Server health and ping
    final pingRes = await widget.apiService.pingServer();
    final health = pingRes['health'] as ServerHealth? ?? ServerHealth.offline();
    final latency = pingRes['latencyMs'] as int?;

    // 2. Fetch PC Config from server
    if (health.isOnline) {
      final pcConfig = await widget.apiService.fetchPcConfig();
      if (pcConfig != null && mounted) {
        setState(() {
          _keyController.text = pcConfig['api_key'] ?? '';
          _fastMode = pcConfig['fast_mode'] ?? false;
          _snapToBubbles = pcConfig['snap_to_bubbles'] ?? true;
          _maskPadding = pcConfig['mask_padding'] is num
              ? (pcConfig['mask_padding'] as num).toInt()
              : 5;
          _iopaintEnabled = pcConfig['iopaint_enabled'] ?? true;
          _iopaintAdaptive = pcConfig['iopaint_adaptive'] ?? true;
          _iopaintUrlController.text =
              pcConfig['iopaint_server_url'] ?? 'http://127.0.0.1:8080';
          _iopaintModel = pcConfig['iopaint_model'] ?? 'anime-lama';
          _iopaintDilation = pcConfig['iopaint_dilation'] is num
              ? (pcConfig['iopaint_dilation'] as num).toInt()
              : 5;
        });
      }
    }

    if (!mounted) return;
    setState(() {
      _health = health;
      _pingLatency = latency;
      _isLoadingConfig = false;
    });
  }

  Future<void> _saveAndSyncToPc() async {
    if (!mounted) return;
    setState(() => _isSavingConfig = true);

    // 1. Save Base URL locally
    await widget.apiService.updateBaseUrl(_urlController.text.trim());

    // 2. Build full PC config payload
    final payload = {
      'api_key': _keyController.text.trim(),
      'fast_mode': _fastMode,
      'snap_to_bubbles': _snapToBubbles,
      'mask_padding': _maskPadding,
      'iopaint_enabled': _iopaintEnabled,
      'iopaint_adaptive': _iopaintAdaptive,
      'iopaint_server_url': _iopaintUrlController.text.trim(),
      'iopaint_model': _iopaintModel,
      'iopaint_dilation': _iopaintDilation,
    };

    // 3. Send and persist into gui_config.json on PC
    final res = await widget.apiService.savePcConfig(payload);
    if (!mounted) return;
    setState(() => _isSavingConfig = false);

    if (res['success'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('تم حفظ الإعدادات وتحديثها على السيرفر بنجاح! 💾✨'),
          backgroundColor: AppTheme.accentEmerald,
        ),
      );
      _loadAndSyncFromPc();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('تم حفظ الرابط محلياً (السيرفر غير متصل للمزامنة)'),
          backgroundColor: AppTheme.primaryCyan,
        ),
      );
    }
  }

  Future<void> _startIOPaintServer() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('جاري إرسال أمر تشغيل IOPaint على الكمبيوتر... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );
    final res = await widget.apiService.startIOPaint();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'تم إرسال الأمر'),
          backgroundColor:
              res['success'] == true ? AppTheme.accentEmerald : AppTheme.accentRose,
        ),
      );
      _loadAndSyncFromPc();
    }
  }

  Future<void> _stopIOPaintServer() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('جاري إرسال أمر إيقاف IOPaint وتفريغ كارت الشاشة... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );
    final res = await widget.apiService.stopIOPaint();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'تم إرسال الأمر'),
          backgroundColor:
              res['success'] == true ? AppTheme.accentEmerald : AppTheme.accentRose,
        ),
      );
      _loadAndSyncFromPc();
    }
  }

  Future<void> _launchPcGui() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('جاري فتح برنامج SmartCleaner على شاشة الكمبيوتر... 🚀'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );
    final res = await widget.apiService.launchPcGui();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'تم إرسال أمر الفتح'),
          backgroundColor:
              res['success'] == true ? AppTheme.accentEmerald : AppTheme.accentRose,
        ),
      );
    }
  }

  Future<void> _closePcGui() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('جاري إغلاق برنامج SmartCleaner على الكمبيوتر... ⏳'),
        backgroundColor: AppTheme.primaryCyan,
      ),
    );
    final res = await widget.apiService.closePcGui();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? 'تم إرسال أمر الإغلاق'),
          backgroundColor:
              res['success'] == true ? AppTheme.accentEmerald : AppTheme.accentRose,
        ),
      );
    }
  }

  Future<void> _confirmShutdownServer() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: TextDirection.rtl,
        child: AlertDialog(
          backgroundColor: AppTheme.cardDark,
          title: const Row(
            children: [
              Icon(Icons.power_settings_new_rounded, color: AppTheme.accentRose),
              SizedBox(width: 8),
              Text('إغلاق خادم الكمبيوتر',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: const Text(
            'هل أنت متأكد من إغلاق خادم SmartCleaner وخدمات IOPaint على الكمبيوتر؟\n\nسيتم تحرير كافة موارد كارت الشاشة والذاكرة فوراً، وستحتاج لإعادة تشغيل Run_Server.bat على الكمبيوتر لاحقاً عند الرغبة في المعالجة.',
            style: TextStyle(fontSize: 12.5, color: Color(0xFFCBD5E1), height: 1.45),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('إلغاء', style: TextStyle(color: Color(0xFF94A3B8))),
            ),
            ElevatedButton.icon(
              onPressed: () => Navigator.pop(ctx, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.accentRose,
                foregroundColor: Colors.white,
              ),
              icon: const Icon(Icons.power_settings_new_rounded, size: 16),
              label: const Text('إغلاق السيرفر الآن'),
            ),
          ],
        ),
      ),
    );

    if (confirm == true) {
      final res = await widget.apiService.shutdownServer();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(res['message'] ?? 'تم إغلاق الخادم'),
            backgroundColor: AppTheme.accentRose,
          ),
        );
        _loadAndSyncFromPc();
      }
    }
  }

  @override
  void dispose() {
    _tabController.dispose();
    _urlController.dispose();
    _keyController.dispose();
    _iopaintUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isOnline = _health?.isOnline == true;

    return Directionality(
      textDirection: TextDirection.rtl,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('إعدادات الاتصال والمعالجة'),
          actions: [
            IconButton(
              tooltip: 'فحص الاتصال ومزامنة الإعدادات',
              icon: _isLoadingConfig
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.sync_rounded),
              onPressed: _isLoadingConfig ? null : _loadAndSyncFromPc,
            ),
          ],
          bottom: TabBar(
            controller: _tabController,
            indicatorColor: AppTheme.primaryCyan,
            labelColor: AppTheme.primaryCyan,
            unselectedLabelColor: const Color(0xFF94A3B8),
            labelStyle:
                const TextStyle(fontSize: 13, fontWeight: FontWeight.bold),
            tabs: const [
              Tab(
                icon: Icon(Icons.link_rounded, size: 18),
                text: 'طريقة الاتصال',
              ),
              Tab(
                icon: Icon(Icons.tune_rounded, size: 18),
                text: 'خيارات الذكاء الاصطناعي',
              ),
              Tab(
                icon: Icon(Icons.help_outline_rounded, size: 18),
                text: 'دليل التوصيل',
              ),
            ],
          ),
        ),
        body: TabBarView(
          controller: _tabController,
          children: [
            _buildConnectionTab(isOnline),
            _buildAiSettingsTab(isOnline),
            _buildGuideTab(),
          ],
        ),
        bottomNavigationBar: Container(
          padding: const EdgeInsets.all(14),
          color: AppTheme.surfaceDark,
          child: SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton.icon(
              onPressed: _isSavingConfig ? null : _saveAndSyncToPc,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.accentEmerald,
                foregroundColor: Colors.black,
              ),
              icon: _isSavingConfig
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.black,
                      ),
                    )
                  : const Icon(Icons.save_as_rounded),
              label: const Text(
                'حفظ وتطبيق الإعدادات 💾',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ==========================================
  // TAB 1: CONNECTION TARGET & DIAGNOSTICS
  // ==========================================
  Widget _buildConnectionTab(bool isOnline) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // 1. Live Diagnostic Banner
        Card(
          color: isOnline
              ? AppTheme.accentEmerald.withValues(alpha: 0.12)
              : AppTheme.accentRose.withValues(alpha: 0.12),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: BorderSide(
              color: isOnline ? AppTheme.accentEmerald : AppTheme.accentRose,
              width: 1,
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Row(
                        children: [
                          Icon(
                            isOnline
                                ? Icons.cloud_done_rounded
                                : Icons.cloud_off_rounded,
                            color: isOnline
                                ? AppTheme.accentEmerald
                                : AppTheme.accentRose,
                            size: 22,
                          ),
                          const SizedBox(width: 8),
                          Flexible(
                            child: Text(
                              isOnline ? 'السيرفر متصل ويعمل بنجاح ✅' : 'السيرفر غير متصل ⚠️',
                              overflow: TextOverflow.ellipsis,
                              maxLines: 1,
                              style: TextStyle(
                                fontSize: 13.5,
                                fontWeight: FontWeight.bold,
                                color: isOnline
                                    ? AppTheme.accentEmerald
                                    : AppTheme.accentRose,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isOnline && _pingLatency != null && _pingLatency! > 0)
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 7, vertical: 3),
                        decoration: BoxDecoration(
                          color:
                              AppTheme.accentEmerald.withValues(alpha: 0.2),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                              color: AppTheme.accentEmerald
                                  .withValues(alpha: 0.4)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.bolt_rounded,
                                size: 12, color: AppTheme.accentEmerald),
                            const SizedBox(width: 2),
                            Text(
                              '${_pingLatency}ms',
                              style: const TextStyle(
                                fontSize: 10.5,
                                fontWeight: FontWeight.bold,
                                color: AppTheme.accentEmerald,
                              ),
                            ),
                          ],
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 8),
                if (isOnline) ...[
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      _buildMiniBadge(
                        label: _health?.serverName ?? 'FastTypeR Server',
                        icon: Icons.computer_rounded,
                        color: AppTheme.primaryCyan,
                      ),
                      _buildMiniBadge(
                        label: _health?.iopaintOnline == true
                            ? 'IOPaint جاهز 🎨'
                            : 'IOPaint غير مفعل',
                        icon: Icons.brush_rounded,
                        color: _health?.iopaintOnline == true
                            ? AppTheme.accentEmerald
                            : const Color(0xFF64748B),
                      ),
                      _buildMiniBadge(
                        label: _health?.geminiConfigured == true
                            ? 'Gemini مفعل 🤖'
                            : 'بدون Gemini',
                        icon: Icons.psychology_rounded,
                        color: _health?.geminiConfigured == true
                            ? const Color(0xFFC084FC)
                            : const Color(0xFF64748B),
                      ),
                    ],
                  ),
                ] else ...[
                  const Text(
                    'تأكد من تشغيل السيرفر على الكمبيوتر (Run_Server.bat) أو تشغيل جلسة Google Colab GPU.',
                    style: TextStyle(fontSize: 11, color: Color(0xFF94A3B8)),
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),

        // 2. Clear Destination Selector
        _buildSectionHeader(
          title: 'اختر السيرفر الذي ترغب بالاتصال به:',
          icon: Icons.hub_rounded,
        ),
        const SizedBox(height: 8),

        // Category Segment
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: const Color(0xFF0F172A),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppTheme.borderDark),
          ),
          child: Row(
            children: [
              Expanded(
                child: GestureDetector(
                  onTap: () => setState(() => _serverCategory = 0),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                    decoration: BoxDecoration(
                      color: _serverCategory == 0
                          ? AppTheme.cardDark
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                      border: _serverCategory == 0
                          ? Border.all(
                              color: AppTheme.primaryCyan
                                  .withValues(alpha: 0.5))
                          : null,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.laptop_chromebook_rounded,
                          size: 15,
                          color: _serverCategory == 0
                              ? AppTheme.primaryCyan
                              : const Color(0xFF94A3B8),
                        ),
                        const SizedBox(width: 5),
                        Flexible(
                          child: Text(
                            '1. سيرفر الكمبيوتر',
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: _serverCategory == 0
                                  ? FontWeight.bold
                                  : FontWeight.normal,
                              color: _serverCategory == 0
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
                  onTap: () => setState(() => _serverCategory = 1),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
                    decoration: BoxDecoration(
                      color: _serverCategory == 1
                          ? AppTheme.cardDark
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(8),
                      border: _serverCategory == 1
                          ? Border.all(
                              color: AppTheme.accentEmerald
                                  .withValues(alpha: 0.5))
                          : null,
                    ),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.cloud_queue_rounded,
                          size: 15,
                          color: _serverCategory == 1
                              ? AppTheme.accentEmerald
                              : const Color(0xFF94A3B8),
                        ),
                        const SizedBox(width: 5),
                        Flexible(
                          child: Text(
                            '2. كولاب (Colab GPU)',
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                            style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: _serverCategory == 1
                                  ? FontWeight.bold
                                  : FontWeight.normal,
                              color: _serverCategory == 1
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

        // 3. Server Input Form & Guidance for Selected Category
        if (_serverCategory == 0) ...[
          // PC SERVER CARD
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: const [
                      Icon(Icons.desktop_windows_rounded,
                          size: 18, color: AppTheme.primaryCyan),
                      SizedBox(width: 8),
                      Text(
                        'الاتصال بسيرفر الكمبيوتر المنزلي:',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'يتطلب تشغيل ملف Run_Server.bat على كمبيوترك.',
                    style: TextStyle(fontSize: 11, color: Color(0xFF94A3B8)),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _urlController,
                    textDirection: TextDirection.ltr,
                    style: const TextStyle(fontSize: 13),
                    decoration: InputDecoration(
                      labelText: 'رابط خادم الكمبيوتر (LAN IP أو Ngrok)',
                      hintText: 'http://192.168.1.5:8000 أو Ngrok',
                      prefixIcon: const Icon(Icons.dns_rounded),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.content_paste_rounded, size: 18),
                        tooltip: 'لصق من الحافظة',
                        onPressed: _pasteServerUrl,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    'اختر وضع الاتصال بالكمبيوتر:',
                    style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFFCBD5E1)),
                  ),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      ActionChip(
                        avatar: const Icon(Icons.wifi_rounded,
                            size: 15, color: AppTheme.primaryCyan),
                        label: const Text('🏠 واي فاي محلي (192.168.1.5)',
                            style: TextStyle(fontSize: 11)),
                        backgroundColor: AppTheme.cardDark,
                        onPressed: () {
                          _urlController.text = 'http://192.168.1.5:8000';
                          _saveAndSyncToPc();
                        },
                      ),
                      ActionChip(
                        avatar: const Icon(Icons.paste_rounded,
                            size: 15, color: Color(0xFFC084FC)),
                        label: const Text('📋 لصق رابط Ngrok من الحافظة',
                            style: TextStyle(fontSize: 11)),
                        backgroundColor: AppTheme.cardDark,
                        onPressed: () {
                          _pasteServerUrl();
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      '💡 نصيحة: عندما تكون في البيت ومتصلاً بنفس الواي فاي مع الكمبيوتر، استخدم IP الواي فاي (مثل 192.168.1.5) لأنه أسرع ولا يستهلك باقة إطلاقاً.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF94A3B8), height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),

          // REMOTE PC POWER & APPS CONTROL CARD
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: const [
                      Icon(Icons.power_settings_new_rounded,
                          size: 18, color: AppTheme.accentEmerald),
                      SizedBox(width: 8),
                      Text(
                        'التحكم في برامج وخادم الكمبيوتر 🖥️',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'يمكنك فتح أو إغلاق برنامج SmartCleaner وخوادم الذكاء الاصطناعي على الكمبيوتر لتوفير الموارد وكارت الشاشة:',
                    style: TextStyle(
                        fontSize: 11, color: Color(0xFF94A3B8), height: 1.4),
                  ),
                  const SizedBox(height: 12),

                  // 1. FastTypeR GUI Control
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: isOnline ? _launchPcGui : null,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppTheme.primaryCyan,
                            side: const BorderSide(color: AppTheme.primaryCyan),
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.open_in_new_rounded, size: 15),
                          label: const Text('فتح البرنامج على PC 🚀',
                              style: TextStyle(fontSize: 11)),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: isOnline ? _closePcGui : null,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppTheme.accentRose,
                            side: const BorderSide(color: AppTheme.accentRose),
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.close_rounded, size: 15),
                          label: const Text('إغلاق البرنامج على PC ❌',
                              style: TextStyle(fontSize: 11)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),

                  // 2. IOPaint AI Server Control
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: isOnline ? _startIOPaintServer : null,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: AppTheme.accentEmerald,
                            side: const BorderSide(
                                color: AppTheme.accentEmerald),
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.play_arrow_rounded, size: 16),
                          label: const Text('تشغيل IOPaint ▶️',
                              style: TextStyle(fontSize: 11)),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: isOnline ? _stopIOPaintServer : null,
                          style: OutlinedButton.styleFrom(
                            foregroundColor: const Color(0xFFF59E0B),
                            side: const BorderSide(color: Color(0xFFF59E0B)),
                            padding: const EdgeInsets.symmetric(vertical: 10),
                            shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10)),
                          ),
                          icon: const Icon(Icons.stop_rounded, size: 16),
                          label: const Text('إيقاف IOPaint (تفريغ GPU) ⏹️',
                              style: TextStyle(fontSize: 11)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Divider(height: 1, color: AppTheme.borderDark),
                  const SizedBox(height: 12),

                  // 3. Shutdown Server Completely
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: isOnline ? _confirmShutdownServer : null,
                      style: ElevatedButton.styleFrom(
                        backgroundColor:
                            AppTheme.accentRose.withValues(alpha: 0.15),
                        foregroundColor: AppTheme.accentRose,
                        side: const BorderSide(color: AppTheme.accentRose),
                        padding: const EdgeInsets.symmetric(vertical: 11),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.power_settings_new_rounded,
                          size: 17),
                      label: const Text(
                        'إغلاق خادم SmartCleaner بالكامل على الكمبيوتر 🛑',
                        style: TextStyle(
                            fontSize: 12, fontWeight: FontWeight.bold),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ] else ...[
          // COLAB CLOUD GPU CARD
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: const [
                      Icon(Icons.cloud_circle_rounded,
                          size: 20, color: AppTheme.accentEmerald),
                      SizedBox(width: 8),
                      Text(
                        'الاتصال بسيرفر Google Colab السحابي (GPU):',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'يعمل على كارت شاشة Nvidia T4 مجاناً وبسرعة خارقة دون الحاجة لتشغيل جهاز الكمبيوتر.',
                    style: TextStyle(fontSize: 11, color: Color(0xFF94A3B8)),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _urlController,
                    textDirection: TextDirection.ltr,
                    style: const TextStyle(fontSize: 13),
                    decoration: InputDecoration(
                      labelText: 'رابط نفق كولاب (Colab Ngrok URL)',
                      hintText: 'https://xxxx-xx-xx.ngrok-free.dev',
                      prefixIcon: const Icon(Icons.link_rounded),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.content_paste_rounded, size: 18),
                        tooltip: 'لصق رابط كولاب من الحافظة',
                        onPressed: _pasteServerUrl,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _pasteServerUrl,
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppTheme.accentEmerald,
                        side: const BorderSide(color: AppTheme.accentEmerald),
                        padding: const EdgeInsets.symmetric(vertical: 10),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                        ),
                      ),
                      icon: const Icon(Icons.content_paste_rounded, size: 16),
                      label: const Text('لصق رابط Colab Ngrok وتحديث الاتصال 📋'),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: const Color(0xFF0F172A),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      '⚡ مميزات وضع كولاب: تنزيل فصول Google Drive بسرعة الجيجابت + كشف وتبييض بالذكاء الاصطناعي على كارت GPU مجاناً.',
                      style: TextStyle(fontSize: 11, color: Color(0xFF94A3B8), height: 1.4),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }

  // ==========================================
  // TAB 2: AI & PROCESSING OPTIONS
  // ==========================================
  Widget _buildAiSettingsTab(bool isOnline) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // 1. Gemini API Key
        _buildSectionHeader(
          title: '1. مفتاح الذكاء الاصطناعي (Gemini API Key)',
          icon: Icons.key_rounded,
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: _keyController,
                  textDirection: TextDirection.ltr,
                  obscureText: _obscureApiKey,
                  decoration: InputDecoration(
                    hintText: 'AIzaSy...',
                    prefixIcon: const Icon(Icons.vpn_key_rounded),
                    suffixIcon: IconButton(
                      icon: Icon(_obscureApiKey
                          ? Icons.visibility_rounded
                          : Icons.visibility_off_rounded),
                      onPressed: () =>
                          setState(() => _obscureApiKey = !_obscureApiKey),
                    ),
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'المفتاح المستخدم في مطابقة الترجمة العربية دلالياً (Gemini 3.x Flash).',
                  style: TextStyle(fontSize: 11, color: Color(0xFF64748B)),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),

        // 2. Extraction & Bubble Options
        _buildSectionHeader(
          title: '2. خيارات استخراج النصوص والفقاعات',
          icon: Icons.tune_rounded,
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('الوضع فائق السرعة (Fast Mode)'),
                  subtitle: const Text(
                      'تجاوز الـ OCR الياباني والترتيب المكاني المباشر لتوفير الوقت.'),
                  value: _fastMode,
                  activeThumbColor: AppTheme.primaryCyan,
                  onChanged: (v) => setState(() => _fastMode = v),
                ),
                const Divider(height: 1, color: AppTheme.borderDark),
                SwitchListTile(
                  title: const Text('محاذاة دقيقة للفقاعات (Snap to Bubbles)'),
                  subtitle: const Text(
                      'تحديد حدود الفقاعة بدقة كونتور Photoshop Magic Wand.'),
                  value: _snapToBubbles,
                  activeThumbColor: const Color(0xFFC084FC),
                  onChanged: (v) => setState(() => _snapToBubbles = v),
                ),
                const Divider(height: 1, color: AppTheme.borderDark),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'حشوة القناع الإضافية: $_maskPadding px',
                              style: const TextStyle(
                                  fontSize: 14, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            const Text(
                              'توسيع إحداثيات الفقاعة بمقدار بكسلات إضافية.',
                              style: TextStyle(
                                  fontSize: 11, color: Color(0xFF94A3B8)),
                            ),
                          ],
                        ),
                      ),
                      Slider(
                        value: _maskPadding.toDouble(),
                        min: 0,
                        max: 50,
                        divisions: 50,
                        activeColor: AppTheme.primaryCyan,
                        onChanged: (v) =>
                            setState(() => _maskPadding = v.toInt()),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 18),

        // 3. Inpainting Options (IOPaint)
        _buildSectionHeader(
          title: '3. إعدادات تنظيف وتبييض الصور (IOPaint AI)',
          icon: Icons.brush_rounded,
        ),
        const SizedBox(height: 8),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('تفعيل التنظيف الذكي (Enable Inpainting) 🧹'),
                  subtitle: const Text(
                      'إزالة النصوص وتبييض الفقاعات تلقائياً عبر نموذج IOPaint.'),
                  value: _iopaintEnabled,
                  activeThumbColor: AppTheme.accentEmerald,
                  onChanged: (v) => setState(() => _iopaintEnabled = v),
                ),
                const Divider(height: 1, color: AppTheme.borderDark),
                SwitchListTile(
                  title: const Text('التنظيف التكيفي الذكي (Smart Adaptive) ⚡'),
                  subtitle: const Text(
                      'تبييض الفقاعات البيضاء محلياً في <0.005s وتوجيه المعقد فقط لـ AI.'),
                  value: _iopaintAdaptive,
                  activeThumbColor: AppTheme.primaryCyan,
                  onChanged: (v) => setState(() => _iopaintAdaptive = v),
                ),
                const Divider(height: 1, color: AppTheme.borderDark),
                // Model Dropdown
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        '🧠 نموذج IOPaint:',
                        style: TextStyle(
                            fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                      DropdownButton<String>(
                        value: _iopaintModels.contains(_iopaintModel)
                            ? _iopaintModel
                            : _iopaintModels.first,
                        dropdownColor: AppTheme.cardDark,
                        borderRadius: BorderRadius.circular(12),
                        items: _iopaintModels.map((m) {
                          return DropdownMenuItem<String>(
                            value: m,
                            child:
                                Text(m, style: const TextStyle(fontSize: 13)),
                          );
                        }).toList(),
                        onChanged: (v) {
                          if (v != null) {
                            setState(() => _iopaintModel = v);
                          }
                        },
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1, color: AppTheme.borderDark),
                // Dilation Slider
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '⭕ تمديد القناع (Dilation): $_iopaintDilation px',
                              style: const TextStyle(
                                  fontSize: 14, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            const Text(
                              'تمديد قناع التبييض لضمان محو حواف النصوص.',
                              style: TextStyle(
                                  fontSize: 11, color: Color(0xFF94A3B8)),
                            ),
                          ],
                        ),
                      ),
                      Slider(
                        value: _iopaintDilation.toDouble(),
                        min: 0,
                        max: 30,
                        divisions: 30,
                        activeColor: AppTheme.accentEmerald,
                        onChanged: (v) =>
                            setState(() => _iopaintDilation = v.toInt()),
                      ),
                    ],
                  ),
                ),
                if (_serverCategory == 0) ...[
                  const Divider(height: 1, color: AppTheme.borderDark),
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        TextField(
                          controller: _iopaintUrlController,
                          textDirection: TextDirection.ltr,
                          decoration: const InputDecoration(
                            labelText: 'رابط خادم IOPaint على الكمبيوتر',
                            hintText: 'http://127.0.0.1:8080',
                            prefixIcon: Icon(Icons.settings_ethernet_rounded),
                          ),
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: isOnline ? _startIOPaintServer : null,
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: AppTheme.accentEmerald,
                                  side: const BorderSide(
                                      color: AppTheme.accentEmerald),
                                  padding:
                                      const EdgeInsets.symmetric(vertical: 10),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                ),
                                icon: const Icon(Icons.play_circle_filled_rounded, size: 16),
                                label:
                                    const Text('تشغيل IOPaint ▶️', style: TextStyle(fontSize: 11.5)),
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: OutlinedButton.icon(
                                onPressed: isOnline ? _stopIOPaintServer : null,
                                style: OutlinedButton.styleFrom(
                                  foregroundColor: const Color(0xFFF59E0B),
                                  side: const BorderSide(
                                      color: Color(0xFFF59E0B)),
                                  padding:
                                      const EdgeInsets.symmetric(vertical: 10),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(10),
                                  ),
                                ),
                                icon: const Icon(Icons.stop_circle_outlined, size: 16),
                                label:
                                    const Text('إيقاف IOPaint (تفريغ كارت الشاشة) ⏹️', style: TextStyle(fontSize: 11.5)),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ==========================================
  // TAB 3: HELP & CONNECTION FAQ
  // ==========================================
  Widget _buildGuideTab() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _buildSectionHeader(
          title: 'دليل توضيح التوصيل ونفق Ngrok 💡',
          icon: Icons.lightbulb_rounded,
        ),
        const SizedBox(height: 12),
        _buildFaqCard(
          title: 'ما الفرق بين سيرفر الكمبيوتر وسيرفر Google Colab؟',
          body:
              '• سيرفر الكمبيوتر: برنامج SmartCleaner يعمل على جهازك المنزلي، ويستخدم إمكانيات جهازك محلياً.\n• سيرفر كولاب (Colab): يعمل سحابياً على خوادم جوجل بكارت شاشة مجاني قوي (T4 GPU)، ويتيح لك استخراج وتبييض الفصول من هاتفك مباشرة حتى وجهاز الكمبيوتر مغلق.',
          icon: Icons.compare_arrows_rounded,
          color: AppTheme.primaryCyan,
        ),
        const SizedBox(height: 10),
        _buildFaqCard(
          title: 'متى أستخدم نفق Ngrok للكمبيوتر ومتى أستخدم الواي فاي (LAN)؟',
          body:
              '• وأنت في المنزل: اختر الواي فاي المحلي (مثال: http://192.168.1.5:8000) لأنه الأسرع ويوفر باقة الإنترنت.\n• وأنت خارج المنزل: استخدم رابط نفق Ngrok الخاص بالكمبيوتر للاتصال بكمبيوترك عبر الإنترنت.',
          icon: Icons.wifi_protected_setup_rounded,
          color: AppTheme.accentEmerald,
        ),
        const SizedBox(height: 10),
        _buildFaqCard(
          title: 'كيف أحصل على رابط Ngrok الخاص بـ Google Colab؟',
          body:
              'عند تشغيل نوت بوك SmartCleaner على Google Colab، ستظهر لك رسالة تحتوي على رابط Ngrok العام (مثل https://xxxx.ngrok-free.dev). كل ما عليك هو نسخه ولصقه في تبويب كولاب هنا في التطبيق.',
          icon: Icons.cloud_download_rounded,
          color: const Color(0xFFC084FC),
        ),
      ],
    );
  }

  Widget _buildFaqCard({
    required String title,
    required String body,
    required IconData icon,
    required Color color,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: color),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.bold,
                      color: color,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              body,
              style: const TextStyle(
                fontSize: 11.5,
                color: Color(0xFFCBD5E1),
                height: 1.45,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildMiniBadge({
    required String label,
    required IconData icon,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: color),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionHeader({required String title, required IconData icon}) {
    return Row(
      children: [
        Icon(icon, size: 18, color: AppTheme.primaryCyan),
        const SizedBox(width: 8),
        Text(
          title,
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}
