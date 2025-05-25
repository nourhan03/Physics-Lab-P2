from flask import jsonify
from flask_restful import Resource
from services import DevicesReplacementService

from flask_restful import Resource
from services import DeviceSuggestionService

from flask_restful import Resource, reqparse
from flask import jsonify, make_response, request
from services import FutureNeedsService

from flask_restful import Resource
from services import MaintenanceService
from flask import request, jsonify
from flask_restful import Resource
from datetime import datetime
from services import MaintenancePredictionService
from model import Devices, DeviceLabs, Laboratories


from flask_restful import Resource, request
from services import ReservationService
from model import Reservations, Laboratories

from flask_restful import Resource, request
from services import ReservationService
from model import Reservations


class ReservationResource(Resource):
    def put(self, reservation_id):
        try:
            data = request.get_json()
            
            # التحقق من وجود الحجز
            reservation = Reservations.query.get(reservation_id)
            if not reservation:
                return {
                    "success": False,
                    "message": "الحجز غير موجود"
                }, 404

            # التحقق من البيانات المطلوب تحديثها
            allowed_fields = [
                'lab_id', 'experiment_id', 'device_ids',
                'date', 'start_time', 'end_time', 'purpose'
            ]
            
            update_data = {}
            for field in allowed_fields:
                if field in data:
                    update_data[field] = data[field]
            
            if not update_data:
                return {
                    "success": False,
                    "message": "لم يتم تقديم أي بيانات للتحديث"
                }, 400

            # تحديث الحجز
            success, message = ReservationService.update_reservation(
                reservation_id,
                update_data
            )

            if not success:
                return {"success": False, "message": message}, 400

            return {
                "success": True,
                "message": "تم تحديث الحجز بنجاح",
                "reservation_id": reservation_id
            }, 200

        except Exception as e:
            return {
                "success": False,
                "message": f"حدث خطأ أثناء تحديث الحجز: {str(e)}"
            }, 500 


class ReservationListResource(Resource):
    def post(self):
        try:
            data = request.get_json()
            
            # التحقق من البيانات المطلوبة
            required_fields = [
                'user_id', 'lab_id', 'experiment_id', 'device_ids',
                'date', 'start_time', 'end_time', 'purpose'
            ]
            for field in required_fields:
                if field not in data:
                    return {"success": False, "message": f"الحقل {field} مطلوب"}, 400

            # إنشاء الحجز
            reservation_id, message = ReservationService.create_reservation(
                data['user_id'],
                data['lab_id'],
                data['experiment_id'],
                data['device_ids'],
                data['date'],
                data['start_time'],
                data['end_time'],
                data['purpose']
            )

            if not reservation_id:
                return {"success": False, "message": message}, 400

            # التحقق من حالة الحجز
            reservation = Reservations.query.get(reservation_id)
            if reservation.IsAllowed:
                return {
                    "success": True,
                    "message": "تم إنشاء الحجز بنجاح",
                    "reservation_id": reservation_id
                }, 201
            else:
                # الحصول على اسم المعمل
                lab = Laboratories.query.get(data['lab_id'])
                lab_name = lab.LabName if lab else "غير معروف"
                
                return {
                    "success": False,
                    "message": f"{lab_name} محجوز بالفعل",
                    "reservation_id": reservation_id,
                    "status": "تم تسجيل محاولة الحجز"
                }, 400

        except Exception as e:
            return {
                "success": False,
                "message": f"حدث خطأ أثناء إنشاء الحجز: {str(e)}"
            }, 500 


class DeviceMaintenancePredictionResource(Resource):
    def get(self):
        """
        الحصول على قائمة بالأجهزة المتاحة التي تحتاج إلى صيانة متوقعة
        ---
        responses:
          200:
            description: قائمة بتوقعات الصيانة للأجهزة المتاحة
        """
        try:
            maintenance_predictions = MaintenancePredictionService.predict_device_maintenance()
            return jsonify({
                "status": "success",
                "data": maintenance_predictions,
                "message": "تم استرجاع توقعات الصيانة بنجاح"
            })
        except Exception as e:
            return jsonify({
                "status": "error",
                "message": f"حدث خطأ أثناء استرجاع توقعات الصيانة: {str(e)}"
            }), 500
    

class MaintenanceNeededResource(Resource):
    def get(self):
        try:
            success, result = MaintenanceService.get_devices_needing_maintenance()
            
            if not success:
                return {
                    "success": False,
                    "message": result
                }, 500

            return {
                "success": True,
                "message": "تم جلب بيانات الأجهزة وأولويات الصيانة بنجاح",
                "devices": result
            }, 200

        except Exception as e:
            return {
                "success": False,
                "message": f"حدث خطأ أثناء جلب بيانات الأجهزة: {str(e)}"
            }, 500 


class FutureNeedsResource(Resource):
    """واجهة API للاحتياجات المستقبلية من قطع الغيار"""
    
    def get(self):
        """
        الحصول على قائمة قطع الغيار المطلوب شراؤها مستقبلاً
        
        يمكن تصفية النتائج باستخدام المعلمات التالية:
        - priority: الأولوية (عالية، متوسطة، منخفضة)
        - reason: سبب الاحتياج (منخفض المخزون، قرب انتهاء الصلاحية، معدل استهلاك عالي، مطلوبة للصيانة القادمة)
        """
        # استخدام args بدلاً من RequestParser
        priority = request.args.get('priority')
        reason = request.args.get('reason')
        
        # إذا تم تحديد معلمة الأولوية
        if priority:
            if priority not in ["عالية", "متوسطة", "منخفضة"]:
                return {'status': 'error', 'message': "الأولوية غير صالحة"}, 400
            
            result = FutureNeedsService.get_parts_by_priority(priority)
            if 'error' in result:
                return {'status': 'error', 'message': result['error']}, 400
            
            response = make_response(jsonify(result))
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # إذا تم تحديد معلمة السبب
        if reason:
            valid_reasons = ["منخفض المخزون", "قرب انتهاء الصلاحية", "معدل استهلاك عالي", "مطلوبة للصيانة القادمة"]
            if reason not in valid_reasons:
                return {'status': 'error', 'message': "السبب غير صالح"}, 400
            
            result = FutureNeedsService.get_parts_by_reason(reason)
            if 'error' in result:
                return {'status': 'error', 'message': result['error']}, 400
            
            response = make_response(jsonify(result))
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
        
        # بدون تصفية، استرجاع كل الاحتياجات
        result = FutureNeedsService.get_future_spare_parts_needs()
        response = make_response(jsonify(result))
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response

class SuggestDeviceResource(Resource):
    def get(self, device_id):
        success, result = DeviceSuggestionService.get_device_suggestions(device_id)
        
        if not success:
            return {"message": result}, 404 if "غير موجود" in result else 500
            
        return result, 200

class DevicesReplacementResource(Resource):
    """مورد API للأجهزة التي تحتاج إلى استبدال"""
    
    def get(self):
        """
        الحصول على قائمة بالأجهزة التي تحتاج إلى استبدال
        ---
        responses:
          200:
            description: قائمة بالأجهزة التي تحتاج إلى استبدال مع تحليل لكل جهاز
        """
        try:
            devices_for_replacement = DevicesReplacementService.get_devices_for_replacement()
            
            return jsonify({
                "status": "نجاح",
                "data": devices_for_replacement,
                "message": "تم استرجاع قائمة الأجهزة التي تحتاج إلى استبدال بنجاح"
            })
        except Exception as e:
            return jsonify({
                "status": "فشل",
                "message": f"حدث خطأ أثناء استرجاع قائمة الأجهزة: {str(e)}"
            }), 500