import 'package:flutter_test/flutter_test.dart';
import 'package:smartcleaner_mobile/models/batch_model.dart';

void main() {
  test('BubbleItem model parsing test', () {
    final json = {
      'id': 1,
      'bounds': [10.0, 20.0, 100.0, 50.0],
      'text': 'Hello',
      'assigned_translation': 'مرحبا',
      'confidence': 0.95,
      'reading_order': 1,
    };

    final item = BubbleItem.fromJson(json, 1);
    expect(item.id, 1);
    expect(item.assignedTranslation, 'مرحبا');
    expect(item.bounds, [10.0, 20.0, 100.0, 50.0]);
  });

  test('ServerHealth offline model test', () {
    final health = ServerHealth.offline();
    expect(health.isOnline, false);
    expect(health.serverName, 'Offline');
  });
}
