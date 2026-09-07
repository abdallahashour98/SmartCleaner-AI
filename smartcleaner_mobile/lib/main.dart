import 'package:flutter/material.dart';
import 'services/api_service.dart';
import 'theme/app_theme.dart';
import 'screens/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final apiService = ApiService();
  await apiService.loadSavedConfig();

  runApp(SmartCleanerApp(apiService: apiService));
}

class SmartCleanerApp extends StatelessWidget {
  final ApiService apiService;

  const SmartCleanerApp({super.key, required this.apiService});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SmartCleaner Mobile',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.darkTheme,
      home: HomeScreen(apiService: apiService),
    );
  }
}
