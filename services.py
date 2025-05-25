from datetime import datetime, timedelta, date
from model import Users, Laboratories, Experiments, Reservations, Devices, ExperimentDevices, Maintenances, SpareParts
from sqlalchemy import and_, func, not_, or_, select
from extensions import db
import difflib  
import logging

logger = logging.getLogger(__name__)


class ReservationService:
    @staticmethod
    def validate_user_type(user_id):
        user = Users.query.get(user_id)
        if not user:
            return False, "المستخدم غير موجود"
        
        if user.UserType not in ["دكتور", "باحث"]:
            return False, "نوع المستخدم غير مصرح له بالحجز"
            
        return True, user

    @staticmethod
    def validate_lab_availability(lab_id, user_type, date_str, start_time_str, end_time_str, exclude_reservation_id=None):
        lab = Laboratories.query.get(lab_id)
        if not lab:
            return False, "المعمل غير موجود"
            
        if lab.Status != "متاح":
            return False, "المعمل غير متاح حالياً"
            
        # التحقق من نوع المعمل
        if user_type == "دكتور" and lab.Type != "أكاديمي":
            return False, "هذا المعمل مخصص للأبحاث فقط"
        elif user_type == "باحث" and lab.Type != "بحثي":
            return False, "هذا المعمل مخصص للتدريس فقط"

        # التحقق من صحة التاريخ والوقت
        try:
            reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            # التحقق من أن التاريخ في المستقبل
            if reservation_date < date.today():
                return False, "لا يمكن الحجز في تاريخ سابق"
                
            # التحقق من أن وقت البداية قبل وقت النهاية
            start_datetime = datetime.combine(reservation_date, start_time)
            end_datetime = datetime.combine(reservation_date, end_time)
            
            if start_datetime >= end_datetime:
                return False, "وقت البداية يجب أن يكون قبل وقت النهاية"
        except ValueError:
            return False, "صيغة التاريخ أو الوقت غير صحيحة"

        # التحقق من الحجوزات الموجودة
        existing_reservations = Reservations.query.filter(
            Reservations.LabId == lab_id,
            Reservations.Date == reservation_date,
            Reservations.IsAllowed == True
        )
        
        # استثناء الحجز الحالي عند التحديث
        if exclude_reservation_id:
            existing_reservations = existing_reservations.filter(
                Reservations.Id != exclude_reservation_id
            )

        existing_reservations = existing_reservations.join(Users).all()

        for reservation in existing_reservations:
            res_start = datetime.combine(reservation_date, reservation.StartTime)
            res_end = datetime.combine(reservation_date, reservation.EndTime)
            
            # التحقق من التداخل الزمني
            if (start_datetime < res_end and end_datetime > res_start):
                # إذا كان هناك دكتور حاجز المعمل
                if reservation.user.UserType == "دكتور":
                    return False, "المعمل محجوز من قبل دكتور في هذا الوقت"
                # إذا كان المستخدم الحالي دكتور وهناك باحث حاجز
                elif user_type == "دكتور" and reservation.user.UserType == "باحث":
                    return False, "المعمل محجوز من قبل باحث في هذا الوقت"

        return True, lab

    @staticmethod
    def validate_experiment(experiment_id, lab_id, user_type):
        experiment = Experiments.query.get(experiment_id)
        if not experiment:
            return False, "التجربة غير موجودة"
            
        if experiment.LabId != lab_id:
            return False, "التجربة غير متوفرة في هذا المعمل"
            
        if user_type == "دكتور" and experiment.Type != "أكاديمية":
            return False, "هذه التجربة مخصصة للأبحاث فقط"
        elif user_type == "باحث" and experiment.Type != "بحثية":
            return False, "هذه التجربة مخصصة للتدريس فقط"
            
        return True, experiment

    @staticmethod
    def validate_devices(device_ids, experiment_id, date_str, start_time_str, end_time_str, exclude_reservation_id=None):
        try:
            # التحقق من صحة التاريخ والوقت
            reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            # التحقق من أن التاريخ في المستقبل
            if reservation_date < date.today():
                return False, "لا يمكن الحجز في تاريخ سابق"
                
            # التحقق من أن وقت البداية قبل وقت النهاية
            start_datetime = datetime.combine(reservation_date, start_time)
            end_datetime = datetime.combine(reservation_date, end_time)
            
            if start_datetime >= end_datetime:
                return False, "وقت البداية يجب أن يكون قبل وقت النهاية"
            
            valid_devices = []
            for device_id in device_ids:
                device = Devices.query.get(device_id)
                if not device:
                    return False, f"الجهاز رقم {device_id} غير موجود"
                    
                # التحقق من أن الجهاز تابع للتجربة من خلال جدول ExperimentDevices
                experiment_device = ExperimentDevices.query.filter_by(
                    ExperimentId=experiment_id,
                    DeviceId=device_id
                ).first()
                
                if not experiment_device:
                    return False, f"الجهاز رقم {device_id} غير مرتبط بهذه التجربة"
                    
                if device.Status != "متاح":
                    return False, f"الجهاز {device.Name} غير متاح حالياً. الحالة: {device.Status}"
                
                # البحث عن الحجوزات المتداخلة بطريقة أكثر شمولية
                overlapping_reservations = db.session.query(Reservations).filter(
                    Reservations.DeviceId == device_id,
                    Reservations.Date == reservation_date,
                    Reservations.IsAllowed == True,
                    or_(
                        and_(
                            Reservations.StartTime <= start_time,
                            Reservations.EndTime > start_time
                        ),
                        and_(
                            Reservations.StartTime < end_time,
                            Reservations.EndTime >= end_time
                        ),
                        and_(
                            Reservations.StartTime >= start_time,
                            Reservations.EndTime <= end_time
                        )
                    )
                )
                
                # استثناء الحجز الحالي في حالة التحديث
                if exclude_reservation_id:
                    overlapping_reservations = overlapping_reservations.filter(
                        Reservations.Id != exclude_reservation_id
                    )
                
                overlapping_count = overlapping_reservations.count()
                
                if overlapping_count > 0:
                    return False, f"الجهاز {device.Name} محجوز بالفعل في هذا الوقت"
                
                # التحقق من وجود صيانة متداخلة للجهاز
                try:
                    overlapping_maintenance = db.session.query(Maintenances).filter(
                        Maintenances.DeviceId == device_id,
                        or_(
                            and_(
                                Maintenances.StartAt <= datetime.combine(reservation_date, datetime.min.time()),
                                Maintenances.EndAt >= datetime.combine(reservation_date, datetime.min.time())
                            )
                        ),
                        Maintenances.Status != "مكتملة"
                    ).count()
                    
                    if overlapping_maintenance > 0:
                        return False, f"الجهاز {device.Name} في الصيانة في هذا التاريخ"
                except Exception as e:
                    logger.warning(f"خطأ أثناء التحقق من جدول الصيانة: {str(e)}")
                    # استمر في التنفيذ حتى لو لم يتم العثور على جدول الصيانة
                    pass
                    
                valid_devices.append(device)
                
            return True, valid_devices
            
        except Exception as e:
            logger.error(f"خطأ أثناء التحقق من توفر الأجهزة: {str(e)}")
            return False, f"حدث خطأ أثناء التحقق من توفر الأجهزة: {str(e)}"

    @staticmethod
    def calculate_hours(start_time_str, end_time_str, date_str):
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        start_datetime = datetime.combine(date, start_time)
        end_datetime = datetime.combine(date, end_time)
        return (end_datetime - start_datetime).total_seconds() / 3600

    @staticmethod
    def deduct_reservation_hours(reservation):
        """تقليل ساعات الحجز القديم"""
        hours = ReservationService.calculate_hours(
            reservation.StartTime.strftime("%H:%M"),
            reservation.EndTime.strftime("%H:%M"),
            reservation.Date.strftime("%Y-%m-%d")
        )
        
        # تقليل ساعات المعمل
        lab = Laboratories.query.get(reservation.LabId)
        lab.UsageHours -= hours
        lab.TotalOperatingHours -= hours
        
        # تقليل ساعات الأجهزة
        devices = Devices.query.join(Reservations).filter(
            Reservations.Id == reservation.Id
        ).all()
        
        for device in devices:
            device.CurrentHour -= hours
            device.TotalOperatingHours -= hours
            
        # تقليل عدد مرات إجراء التجربة
        experiment = Experiments.query.get(reservation.ExperimentId)
        experiment.CompletedCount -= 1
        
        db.session.commit()

    @staticmethod
    def add_reservation_hours(reservation, devices, lab, experiment, hours):
        """إضافة ساعات الحجز الجديد"""
        # إضافة ساعات المعمل
        lab.UsageHours += hours
        lab.TotalOperatingHours += hours
        
        # إضافة ساعات الأجهزة
        for device in devices:
            device.CurrentHour += hours
            device.TotalOperatingHours += hours
            
        # زيادة عدد مرات إجراء التجربة
        experiment.CompletedCount += 1
        
        db.session.commit()

    @staticmethod
    def update_reservation(reservation_id, update_data):
        try:
            # الحصول على الحجز الحالي
            reservation = Reservations.query.get(reservation_id)
            if not reservation:
                return False, "الحجز غير موجود"

            # التحقق من نوع المستخدم
            user_valid, user = ReservationService.validate_user_type(reservation.UserId)
            if not user_valid:
                return False, user

            # تحديد البيانات المطلوب تحديثها
            lab_id = update_data.get('lab_id', reservation.LabId)
            experiment_id = update_data.get('experiment_id', reservation.ExperimentId)
            device_ids = update_data.get('device_ids', [reservation.DeviceId])
            date_str = update_data.get('date', reservation.Date.strftime("%Y-%m-%d"))
            start_time_str = update_data.get('start_time', reservation.StartTime.strftime("%H:%M"))
            end_time_str = update_data.get('end_time', reservation.EndTime.strftime("%H:%M"))
            purpose = update_data.get('purpose', reservation.Purpose)

            # التحقق من توفر المعمل
            lab_valid, lab = ReservationService.validate_lab_availability(
                lab_id, user.UserType, date_str, start_time_str, end_time_str,
                exclude_reservation_id=reservation_id
            )
            if not lab_valid:
                return False, lab

            # التحقق من التجربة
            exp_valid, experiment = ReservationService.validate_experiment(
                experiment_id, lab_id, user.UserType
            )
            if not exp_valid:
                return False, experiment

            # التحقق من الأجهزة
            devices_valid, devices = ReservationService.validate_devices(
                device_ids, experiment_id, date_str, start_time_str, end_time_str,
                exclude_reservation_id=reservation_id
            )
            if not devices_valid:
                return False, devices

            # حساب ساعات الحجز الجديد
            new_hours = ReservationService.calculate_hours(
                start_time_str, end_time_str, date_str
            )

            # تقليل ساعات الحجز القديم
            ReservationService.deduct_reservation_hours(reservation)

            # تحديث بيانات الحجز
            reservation.LabId = lab_id
            reservation.ExperimentId = experiment_id
            reservation.Date = datetime.strptime(date_str, "%Y-%m-%d").date()
            reservation.StartTime = datetime.strptime(start_time_str, "%H:%M").time()
            reservation.EndTime = datetime.strptime(end_time_str, "%H:%M").time()
            reservation.Purpose = purpose
            reservation.IsAllowed = True

            # إضافة ساعات الحجز الجديد
            ReservationService.add_reservation_hours(
                reservation, devices, lab, experiment, new_hours
            )

            # حفظ التغييرات
            db.session.commit()
            return True, "تم تحديث الحجز بنجاح"

        except Exception as e:
            db.session.rollback()
            return False, f"حدث خطأ أثناء تحديث الحجز: {str(e)}" 

class ReservationService:
    @staticmethod
    def validate_user_type(user_id):
        user = Users.query.get(user_id)
        if not user:
            return False, "المستخدم غير موجود"
        
        if user.UserType not in ["دكتور", "باحث"]:
            return False, "نوع المستخدم غير مصرح له بالحجز"
            
        return True, user

    @staticmethod
    def validate_lab_availability(lab_id, user_type, date_str, start_time_str, end_time_str, exclude_reservation_id=None):
        try:
            lab = Laboratories.query.get(lab_id)
            if not lab:
                return False, "المعمل غير موجود"
                
            if lab.Status != "متاح":
                return False, f"المعمل غير متاح حالياً. الحالة: {lab.Status}"
                
            # التحقق من نوع المعمل
            if user_type == "دكتور" and lab.Type != "أكاديمي":
                return False, "هذا المعمل مخصص للأبحاث فقط"
            elif user_type == "باحث" and lab.Type != "بحثي":
                return False, "هذا المعمل مخصص للتدريس فقط"

            # تحويل التاريخ والوقت إلى الصيغة المناسبة
            from datetime import date
            reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            # التحقق من صحة الوقت
            if start_time >= end_time:
                return False, "وقت البداية يجب أن يكون قبل وقت النهاية"
            
            # التحقق من التاريخ
            today = date.today()
            if reservation_date < today:
                return False, "لا يمكن الحجز في تاريخ سابق"
            
            # البحث عن الحجوزات المتداخلة
            from sqlalchemy import or_, and_
            overlapping_reservations = db.session.query(Reservations).filter(
                Reservations.LabId == lab_id,
                Reservations.Date == reservation_date,
                Reservations.IsAllowed == True,
                or_(
                    and_(
                        Reservations.StartTime <= start_time,
                        Reservations.EndTime > start_time
                    ),
                    and_(
                        Reservations.StartTime < end_time,
                        Reservations.EndTime >= end_time
                    ),
                    and_(
                        Reservations.StartTime >= start_time,
                        Reservations.EndTime <= end_time
                    )
                )
            )
            
            # استثناء الحجز الحالي في حالة التحديث
            if exclude_reservation_id:
                overlapping_reservations = overlapping_reservations.filter(
                    Reservations.Id != exclude_reservation_id
                )
            
            # التحقق من الحجوزات المتداخلة
            for reservation in overlapping_reservations.join(Users).all():
                # إذا كان هناك دكتور حاجز المعمل
                if reservation.user.UserType == "دكتور":
                    return False, f"المعمل {lab.LabName} محجوز من قبل دكتور في هذا الوقت"
                # إذا كان المستخدم الحالي دكتور وهناك باحث حاجز
                elif user_type == "دكتور" and reservation.user.UserType == "باحث":
                    return False, f"المعمل {lab.LabName} محجوز من قبل باحث في هذا الوقت"
                else:
                    return False, f"المعمل {lab.LabName} محجوز بالفعل في هذا الوقت"

            return True, lab
            
        except Exception as e:
            return False, f"حدث خطأ أثناء التحقق من توفر المعمل: {str(e)}"

    @staticmethod
    def validate_experiment(experiment_id, lab_id, user_type):
        experiment = Experiments.query.get(experiment_id)
        if not experiment:
            return False, "التجربة غير موجودة"
            
        if experiment.LabId != lab_id:
            return False, "التجربة غير متوفرة في هذا المعمل"
            
        if user_type == "دكتور" and experiment.Type != "أكاديمية":
            return False, "هذه التجربة مخصصة للأبحاث فقط"
        elif user_type == "باحث" and experiment.Type != "بحثية":
            return False, "هذه التجربة مخصصة للتدريس فقط"
            
        return True, experiment

    @staticmethod
    def validate_devices(device_ids, experiment_id, date_str, start_time_str, end_time_str, exclude_reservation_id=None):
        try:
            valid_devices = []
            from datetime import date
            from sqlalchemy import or_, and_
            
            # تحويل التاريخ والوقت إلى الصيغة المناسبة
            reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            
            # التحقق من صحة الوقت
            if start_time >= end_time:
                return False, "وقت البداية يجب أن يكون قبل وقت النهاية"
            
            # التحقق من التاريخ
            today = date.today()
            if reservation_date < today:
                return False, "لا يمكن الحجز في تاريخ سابق"
            
            for device_id in device_ids:
                device = Devices.query.get(device_id)
                if not device:
                    return False, f"الجهاز رقم {device_id} غير موجود"
                    
                # التحقق من أن الجهاز تابع للتجربة من خلال جدول ExperimentDevices
                experiment_device = ExperimentDevices.query.filter_by(
                    ExperimentId=experiment_id,
                    DeviceId=device_id
                ).first()
                
                if not experiment_device:
                    return False, f"الجهاز رقم {device_id} غير مرتبط بهذه التجربة"
                    
                if device.Status != "متاح":
                    return False, f"الجهاز {device.Name} غير متاح حالياً. الحالة: {device.Status}"
                    
                # البحث عن الحجوزات المتداخلة
                overlapping_reservations = db.session.query(Reservations).filter(
                    Reservations.DeviceId == device_id,
                    Reservations.Date == reservation_date,
                    Reservations.IsAllowed == True,
                    or_(
                        and_(
                            Reservations.StartTime <= start_time,
                            Reservations.EndTime > start_time
                        ),
                        and_(
                            Reservations.StartTime < end_time,
                            Reservations.EndTime >= end_time
                        ),
                        and_(
                            Reservations.StartTime >= start_time,
                            Reservations.EndTime <= end_time
                        )
                    )
                )
                
                # استثناء الحجز الحالي في حالة التحديث
                if exclude_reservation_id:
                    overlapping_reservations = overlapping_reservations.filter(
                        Reservations.Id != exclude_reservation_id
                    )
                
                if overlapping_reservations.count() > 0:
                    return False, f"الجهاز {device.Name} محجوز في هذا الوقت"
                
                # البحث عن الصيانة المتداخلة - إذا كان جدول Maintenances موجود
                try:
                    from model import Maintenances
                    overlapping_maintenance = db.session.query(Maintenances).filter(
                        Maintenances.DeviceId == device_id,
                        or_(
                            and_(
                                Maintenances.StartAt <= datetime.combine(reservation_date, datetime.min.time()),
                                Maintenances.EndAt >= datetime.combine(reservation_date, datetime.min.time())
                            )
                        ),
                        Maintenances.Status != "مكتملة"
                    ).count()
                    
                    if overlapping_maintenance > 0:
                        return False, f"الجهاز {device.Name} في الصيانة في هذا التاريخ"
                except ImportError:
                    # إذا كان جدول الصيانة غير موجود، تجاهل هذا التحقق
                    pass
                    
                valid_devices.append(device)
                
            return True, valid_devices
            
        except Exception as e:
            return False, f"حدث خطأ أثناء التحقق من توفر الأجهزة: {str(e)}"

    @staticmethod
    def calculate_hours(start_time_str, end_time_str, date_str):
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        start_datetime = datetime.combine(date, start_time)
        end_datetime = datetime.combine(date, end_time)
        return (end_datetime - start_datetime).total_seconds() / 3600

    @staticmethod
    def deduct_reservation_hours(reservation):
        """تقليل ساعات الحجز القديم"""
        hours = ReservationService.calculate_hours(
            reservation.StartTime.strftime("%H:%M"),
            reservation.EndTime.strftime("%H:%M"),
            reservation.Date.strftime("%Y-%m-%d")
        )
        
        # تقليل ساعات المعمل
        lab = Laboratories.query.get(reservation.LabId)
        lab.UsageHours -= hours
        lab.TotalOperatingHours -= hours
        
        # تقليل ساعات الأجهزة
        devices = Devices.query.join(Reservations).filter(
            Reservations.Id == reservation.Id
        ).all()
        
        for device in devices:
            device.CurrentHour -= hours
            device.TotalOperatingHours -= hours
            
        # تقليل عدد مرات إجراء التجربة
        experiment = Experiments.query.get(reservation.ExperimentId)
        experiment.CompletedCount -= 1
        
        db.session.commit()

    @staticmethod
    def add_reservation_hours(reservation, devices, lab, experiment, hours):
        """إضافة ساعات الحجز"""
        # إضافة ساعات المعمل
        lab.UsageHours += hours
        lab.TotalOperatingHours += hours
        
        # إضافة ساعات الأجهزة
        for device in devices:
            device.CurrentHour += hours
            device.TotalOperatingHours += hours
            
        # زيادة عدد مرات إجراء التجربة
        experiment.CompletedCount += 1
        
        db.session.commit()

    @staticmethod
    def update_reservation(reservation_id, update_data):
        try:
            # الحصول على الحجز الحالي
            reservation = Reservations.query.get(reservation_id)
            if not reservation:
                return False, "الحجز غير موجود"

            # التحقق من نوع المستخدم
            user_valid, user = ReservationService.validate_user_type(reservation.UserId)
            if not user_valid:
                return False, user

            # تحديد البيانات المطلوب تحديثها
            lab_id = update_data.get('lab_id', reservation.LabId)
            experiment_id = update_data.get('experiment_id', reservation.ExperimentId)
            device_ids = update_data.get('device_ids', [reservation.DeviceId])
            date_str = update_data.get('date', reservation.Date.strftime("%Y-%m-%d"))
            start_time_str = update_data.get('start_time', reservation.StartTime.strftime("%H:%M"))
            end_time_str = update_data.get('end_time', reservation.EndTime.strftime("%H:%M"))
            purpose = update_data.get('purpose', reservation.Purpose)

            # التحقق من توفر المعمل
            lab_valid, lab = ReservationService.validate_lab_availability(
                lab_id, user.UserType, date_str, start_time_str, end_time_str, reservation.Id
            )
            if not lab_valid:
                return False, lab

            # التحقق من التجربة
            exp_valid, experiment = ReservationService.validate_experiment(
                experiment_id, lab_id, user.UserType
            )
            if not exp_valid:
                return False, experiment

            # التحقق من الأجهزة
            devices_valid, devices = ReservationService.validate_devices(
                device_ids, experiment_id, date_str, start_time_str, end_time_str, reservation.Id
            )
            if not devices_valid:
                return False, devices

            # حساب ساعات الحجز الجديد
            new_hours = ReservationService.calculate_hours(
                start_time_str, end_time_str, date_str
            )

            # تقليل ساعات الحجز القديم
            ReservationService.deduct_reservation_hours(reservation)

            # تحديث بيانات الحجز
            reservation.LabId = lab_id
            reservation.ExperimentId = experiment_id
            reservation.Date = datetime.strptime(date_str, "%Y-%m-%d").date()
            reservation.StartTime = datetime.strptime(start_time_str, "%H:%M").time()
            reservation.EndTime = datetime.strptime(end_time_str, "%H:%M").time()
            reservation.Purpose = purpose
            reservation.IsAllowed = True

            # إضافة ساعات الحجز الجديد
            ReservationService.add_reservation_hours(
                reservation, devices, lab, experiment, new_hours
            )

            # حفظ التغييرات
            db.session.commit()
            return True, "تم تحديث الحجز بنجاح"

        except Exception as e:
            db.session.rollback()
            return False, f"حدث خطأ أثناء تحديث الحجز: {str(e)}"

    @staticmethod
    def create_reservation(user_id, lab_id, experiment_id, device_ids, date_str, start_time_str, end_time_str, purpose):
        try:
            # 1. التحقق من نوع المستخدم
            user_valid, user_result = ReservationService.validate_user_type(user_id)
            if not user_valid:
                return None, user_result
            user = user_result

            # 2. التحقق من المعمل
            lab_valid, lab_result = ReservationService.validate_lab_availability(
                lab_id, user.UserType, date_str, start_time_str, end_time_str
            )
            if not lab_valid:
                # إنشاء حجز مرفوض فقط إذا كان المعمل محجوز في هذا الوقت
                if "محجوز" in lab_result:
                    reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                    end_time = datetime.strptime(end_time_str, "%H:%M").time()
                    
                    reservation = Reservations(
                        UserId=user_id,
                        DeviceId=device_ids[0],
                        LabId=lab_id,
                        ExperimentId=experiment_id,
                        Date=reservation_date,
                        StartTime=start_time,
                        EndTime=end_time,
                        Purpose=purpose,
                        IsAllowed=False
                    )
                    db.session.add(reservation)
                    db.session.commit()
                    return reservation.Id, lab_result
                return None, lab_result
            lab = lab_result

            # 3. التحقق من التجربة
            exp_valid, exp_result = ReservationService.validate_experiment(
                experiment_id, lab_id, user.UserType
            )
            if not exp_valid:
                return None, exp_result
            experiment = exp_result

            # 4. التحقق من الأجهزة
            devices_valid, devices_result = ReservationService.validate_devices(
                device_ids, experiment_id, date_str, start_time_str, end_time_str
            )
            if not devices_valid:
                # إنشاء حجز مرفوض فقط إذا كان الجهاز محجوز في هذا الوقت
                if "محجوز" in devices_result:
                    reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                    start_time = datetime.strptime(start_time_str, "%H:%M").time()
                    end_time = datetime.strptime(end_time_str, "%H:%M").time()
                    
                    reservation = Reservations(
                        UserId=user_id,
                        DeviceId=device_ids[0],
                        LabId=lab_id,
                        ExperimentId=experiment_id,
                        Date=reservation_date,
                        StartTime=start_time,
                        EndTime=end_time,
                        Purpose=purpose,
                        IsAllowed=False
                    )
                    db.session.add(reservation)
                    db.session.commit()
                    return reservation.Id, devices_result
                return None, devices_result
            devices = devices_result

            # حساب عدد ساعات الحجز
            hours_count = ReservationService.calculate_hours(
                start_time_str, end_time_str, date_str
            )

            # إنشاء الحجوزات وتحديث الإحصائيات
            reservation_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()

            reservations = []
            for device in devices:
                reservation = Reservations(
                    UserId=user_id,
                    DeviceId=device.Id,
                    LabId=lab_id,
                    ExperimentId=experiment_id,
                    Date=reservation_date,
                    StartTime=start_time,
                    EndTime=end_time,
                    Purpose=purpose,
                    IsAllowed=True
                )
                reservations.append(reservation)

            # حفظ الحجوزات
            db.session.add_all(reservations)
            db.session.commit()

            # إضافة ساعات الحجز
            ReservationService.add_reservation_hours(
                reservations[0], devices, lab, experiment, hours_count
            )

            return reservations[0].Id, "تم إنشاء الحجز بنجاح"

        except Exception as e:
            db.session.rollback()
            return None, f"حدث خطأ أثناء إنشاء الحجز: {str(e)}" 

class MaintenancePredictionService:
    @staticmethod
    def predict_device_maintenance():
        # الحصول على الأجهزة المتاحة (جميع الأجهزة باستثناء: قيد الصيانة، في الصيانة، غير متاح)
        unavailable_statuses = ["قيد الصيانة", "في الصيانة", "غير متاح"]
        available_devices = Devices.query.filter(not_(Devices.Status.in_(unavailable_statuses))).all()
        
        maintenance_predictions = []
        
        current_date = datetime.now()
        
        for device in available_devices:
            prediction = {
                "Id": device.Id,
                "Name": device.Name,
                "CurrentHour": device.CurrentHour,
                "MaximumHour": device.MaximumHour
            }
            
            # التحقق من ساعات التشغيل للصيانة الدورية
            if device.CurrentHour >= device.MaximumHour * 0.9:  # إذا وصل إلى 90% من الحد الأقصى
                prediction["MaintenanceType"] = "صيانة دورية"
                # حساب التاريخ المتوقع بناءً على معدل استخدام الجهاز
                remaining_hours = device.MaximumHour - device.CurrentHour
                prediction["ExpectedDate"] = (current_date + timedelta(days=remaining_hours/8)).strftime('%Y-%m-%d')  # تقدير 8 ساعات في اليوم
                
                # حساب التكلفة المتوقعة للصيانة
                prediction["ExpectedCost"] = MaintenancePredictionService.get_expected_maintenance_cost(device, "صيانة دورية")
            
            # التحقق من تاريخ المعايرة
            if device.CalibrationInterval is not None and device.LastMaintenanceDate is not None:
                last_calibration = Maintenances.query.filter(
                    Maintenances.DeviceId == device.Id,
                    Maintenances.Type == "معايرة"
                ).order_by(Maintenances.EndAt.desc()).first()
                
                if last_calibration:
                    # حساب تاريخ المعايرة التالية المتوقعة
                    next_calibration_date = last_calibration.EndAt + timedelta(days=device.CalibrationInterval * 30)  # تحويل الشهور إلى أيام
                    
                    # إذا كان موعد المعايرة التالية قريبًا (خلال 30 يوم)
                    if (next_calibration_date - current_date).days <= 30 and (next_calibration_date - current_date).days > 0:
                        # إضافة معايرة متوقعة فقط إذا لم تكن هناك صيانة دورية متوقعة بالفعل أو إذا كانت المعايرة قبل الصيانة الدورية
                        if "MaintenanceType" not in prediction or (
                            datetime.strptime(prediction["ExpectedDate"], '%Y-%m-%d') > next_calibration_date
                        ):
                            prediction["MaintenanceType"] = "معايرة"
                            prediction["ExpectedDate"] = next_calibration_date.strftime('%Y-%m-%d')
                            
                            # حساب التكلفة المتوقعة للمعايرة
                            prediction["ExpectedCost"] = MaintenancePredictionService.get_expected_maintenance_cost(device, "معايرة")
                            
                    # إذا تجاوز موعد المعايرة التالية التاريخ الحالي
                    elif (next_calibration_date - current_date).days <= 0:
                        prediction["MaintenanceType"] = "معايرة متأخرة"
                        prediction["ExpectedDate"] = next_calibration_date.strftime('%Y-%m-%d')
                        
                        # حساب التكلفة المتوقعة للمعايرة
                        prediction["ExpectedCost"] = MaintenancePredictionService.get_expected_maintenance_cost(device, "معايرة")
            
            # إضافة التوقع فقط إذا تم تحديد نوع الصيانة
            if "MaintenanceType" in prediction:
                maintenance_predictions.append(prediction)
        
        return maintenance_predictions
        
    @staticmethod
    def get_expected_maintenance_cost(device, maintenance_type):
        """
        حساب التكلفة المتوقعة للصيانة بناءً على صيانات سابقة للجهاز نفسه أو أجهزة من نفس الفئة
        
        :param device: الجهاز المراد حساب تكلفة صيانته
        :param maintenance_type: نوع الصيانة (صيانة دورية أو معايرة)
        :return: التكلفة المتوقعة للصيانة
        """
        # 1. البحث عن صيانات سابقة لنفس الجهاز ومن نفس النوع
        previous_maintenance = Maintenances.query.filter(
            Maintenances.DeviceId == device.Id,
            Maintenances.Type == maintenance_type
        ).order_by(Maintenances.EndAt.desc()).first()
        
        if previous_maintenance:
            return float(previous_maintenance.Cost)
        
        # 2. إذا لم يتم العثور على صيانات سابقة للجهاز، ابحث عن صيانات لأجهزة من نفس الفئة
        similar_devices = Devices.query.filter(
            Devices.CategoryName == device.CategoryName,
            Devices.Id != device.Id
        ).all()
        
        similar_device_ids = [d.Id for d in similar_devices]
        
        if similar_device_ids:
            # البحث عن أحدث صيانة للأجهزة من نفس الفئة
            similar_maintenance = Maintenances.query.filter(
                Maintenances.DeviceId.in_(similar_device_ids),
                Maintenances.Type == maintenance_type
            ).order_by(Maintenances.EndAt.desc()).first()
            
            if similar_maintenance:
                return float(similar_maintenance.Cost)
        
        # 3. إذا لم يتم العثور على أي صيانات، استخدم متوسط تكلفة جميع الصيانات من نفس النوع
        avg_cost = db.session.query(func.avg(Maintenances.Cost)).filter(
            Maintenances.Type == maintenance_type
        ).scalar()
        
        if avg_cost:
            return float(avg_cost)
        
        # 4. إذا لم يتم العثور على أي شيء، عد بقيمة افتراضية
        return 500.0  # قيمة افتراضية معقولة للصيانة
   

class MaintenanceService:
    @staticmethod
    def calculate_periodic_maintenance_priority(current_hours, max_hours):
        percentage = (current_hours / max_hours) * 100
        if current_hours >= max_hours:
            return "طارئة"
        elif percentage >= 90:
            return "عالية"
        elif 60 <= percentage < 90:
            return "متوسطة"
        else:
            return "ضعيفة"

    @staticmethod
    def calculate_months_between_dates(start_date, end_date):
        # حساب عدد الشهور بين تاريخين
        months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
        if end_date.day < start_date.day:
            months -= 1
        return months

    @staticmethod
    def calculate_calibration_priority(device_id, calibration_interval):
        if not calibration_interval:
            return "غير محدد"

        # استخدام select لتحديد الأعمدة المطلوبة فقط
        stmt = select(Maintenances.EndAt).where(
            and_(
                Maintenances.DeviceId == device_id,
                Maintenances.Type == "معايرة"
            )
        ).order_by(Maintenances.EndAt.desc())
        
        last_calibration = db.session.execute(stmt).first()

        if not last_calibration or not last_calibration[0]:
            return "غير محدد"

        # حساب عدد الشهور منذ آخر معايرة
        months_since_calibration = MaintenanceService.calculate_months_between_dates(
            last_calibration[0],
            datetime.now()
        )
        
        # حساب النسبة المئوية من فترة المعايرة التي مرت
        percentage = (months_since_calibration / calibration_interval) * 100
        
        if months_since_calibration >= calibration_interval:
            return "طارئة"
        elif percentage >= 90:
            return "عالية"
        elif 60 <= percentage < 90:
            return "متوسطة"
        else:
            return "ضعيفة"

    @staticmethod
    def get_last_calibration_date(device_id):
        # استخدام select لتحديد الأعمدة المطلوبة فقط
        stmt = select(Maintenances.EndAt).where(
            and_(
                Maintenances.DeviceId == device_id,
                Maintenances.Type == "معايرة"
            )
        ).order_by(Maintenances.EndAt.desc())
        
        result = db.session.execute(stmt).first()
        return result[0] if result else None

    @staticmethod
    def get_devices_needing_maintenance():
        try:
            # نجلب كل الأجهزة أولاً للتحقق
            all_devices = Devices.query.all()
            print(f"Total devices found: {len(all_devices)}")
            
            # نطبع حالة كل جهاز للتحقق
            for device in all_devices:
                print(f"Device ID: {device.Id}, Name: {device.Name}, Status: {device.Status}")

            # نجلب الأجهزة المتاحة فقط
            devices = Devices.query.filter(
                Devices.Status != ["في الصيانة", "غير متاح"]
            ).all()
            print(f"Available devices: {len(devices)}")

            devices_data = []
            for device in devices:
                # حساب أولوية الصيانة الدورية
                periodic_priority = MaintenanceService.calculate_periodic_maintenance_priority(
                    device.CurrentHour,
                    device.MaximumHour
                )

                # حساب أولوية صيانة المعايرة
                calibration_priority = MaintenanceService.calculate_calibration_priority(
                    device.Id,
                    device.CalibrationInterval
                )

                # تحديد الأولوية النهائية (نأخذ الأعلى أولوية)
                priority_order = {"طارئة": 4, "عالية": 3, "متوسطة": 2, "ضعيفة": 1, "غير محدد": 0}
                final_priority = (
                    periodic_priority if priority_order[periodic_priority] > priority_order[calibration_priority]
                    else calibration_priority
                )

                # الحصول على تاريخ آخر معايرة
                last_calibration_date = MaintenanceService.get_last_calibration_date(device.Id)

                devices_data.append({
                    "device_id": device.Id,
                    "device_name": device.Name,
                    "last_maintenance_date": device.LastMaintenanceDate.strftime("%Y-%m-%d") if device.LastMaintenanceDate else None,
                    "current_hours": device.CurrentHour,
                    "priority": final_priority,
                    "periodic_maintenance_details": {
                        "current_hours": device.CurrentHour,
                        "maximum_hours": device.MaximumHour,
                        "priority": periodic_priority
                    },
                    "calibration_maintenance_details": {
                        "last_calibration_date": last_calibration_date.strftime("%Y-%m-%d") if last_calibration_date else None,
                        "calibration_interval_months": device.CalibrationInterval,
                        "priority": calibration_priority
                    }
                })

            # ترتيب الأجهزة حسب الأولوية
            priority_order = {"طارئة": 4, "عالية": 3, "متوسطة": 2, "ضعيفة": 1, "غير محدد": 0}
            devices_data.sort(key=lambda x: priority_order[x["priority"]], reverse=True)

            return True, devices_data

        except Exception as e:
            return False, f"حدث خطأ أثناء جلب بيانات الأجهزة: {str(e)}" 

class FutureNeedsService:
    """خدمة تحديد الاحتياجات المستقبلية من قطع الغيار"""
    
    @staticmethod
    def get_future_spare_parts_needs():
        """
        تحديد قطع الغيار المطلوب شراؤها مستقبلاً بناءً على المعايير التالية:
        1. قطع الغيار منخفضة المخزون
        2. قطع الغيار التي تقارب انتهاء الصلاحية
        3. قطع الغيار ذات معدل الاستهلاك العالي
        4. قطع الغيار المطلوبة للصيانات القادمة
        """
        # تعريف المتغيرات الزمنية
        today = datetime.now()
        one_month = today + timedelta(days=30)
        two_months = today + timedelta(days=60)
        
        # 1. قطع الغيار منخفضة المخزون
        low_stock_parts = SpareParts.query.filter(
            SpareParts.Quantity <= (SpareParts.MinimumQuantity * 1.2)  # أقل من أو يساوي الحد الأدنى + 20%
        ).all()
        
        # 2. قطع الغيار التي تقارب انتهاء الصلاحية
        expiring_parts = SpareParts.query.filter(
            SpareParts.ExpiryDate.isnot(None),
            SpareParts.ExpiryDate <= two_months,
            SpareParts.Quantity > 0  # فقط القطع التي لا زال هناك مخزون منها
        ).all()
        
        # 3. قطع الغيار ذات معدل الاستهلاك العالي
        high_consumption_parts = []
        parts_with_restock_date = SpareParts.query.filter(
            SpareParts.LastRestockDate.isnot(None),
            SpareParts.Quantity > 0
        ).all()
        
        for part in parts_with_restock_date:
            if part.LastRestockDate:
                days_since_restock = (today - part.LastRestockDate).days
                if days_since_restock > 0:
                    # تقدير الكمية الأصلية عند آخر تخزين
                    # (هذا تقدير بسيط، قد تحتاج لتحسينه إذا كان لديك بيانات أكثر دقة)
                    estimated_original_quantity = part.Quantity * 1.5  # تقدير بسيط
                    consumed_quantity = estimated_original_quantity - part.Quantity
                    
                    # حساب معدل الاستهلاك اليومي
                    daily_consumption_rate = consumed_quantity / days_since_restock if days_since_restock > 0 else 0
                    
                    # تقدير عدد الأيام حتى نفاد المخزون
                    days_until_empty = part.Quantity / daily_consumption_rate if daily_consumption_rate > 0 else 999
                    
                    # إذا كان سينفد في أقل من 45 يوم، أضفه للقائمة
                    if days_until_empty <= 45:
                        part.estimated_days = round(days_until_empty, 2)
                        part.consumption_rate = round(daily_consumption_rate, 2)
                        high_consumption_parts.append(part)
        
        # 4. قطع الغيار المطلوبة للصيانات القادمة
        # الحصول على الصيانات المجدولة في المستقبل القريب
        upcoming_maintenances = Maintenances.query.filter(
            Maintenances.Status.in_(["مجدولة", "قيد التنفيذ", "تم الجدولة"]),
            Maintenances.SchedulingAt > today,
            Maintenances.SchedulingAt <= two_months
        ).all()
        
        # قطع الغيار المرتبطة بالأجهزة التي لديها صيانات قادمة
        maintenance_related_parts = []
        for maintenance in upcoming_maintenances:
            if maintenance.DeviceId:
                device_parts = SpareParts.query.filter_by(DeviceId=maintenance.DeviceId).all()
                for part in device_parts:
                    # تجنب التكرار
                    if part not in maintenance_related_parts:
                        maintenance_related_parts.append(part)
        
        # دمج وترتيب النتائج
        all_parts_list = []
        
        # 1. إضافة قطع الغيار منخفضة المخزون مع التفاصيل
        for part in low_stock_parts:
            stock_percentage = (part.Quantity / part.MinimumQuantity * 100) if part.MinimumQuantity > 0 else 0
            
            # تحديد مستوى الأولوية بناءً على نسبة المخزون
            if part.Quantity <= part.MinimumQuantity:
                priority = "عالية"
                days_to_action = 0  # بحاجة للشراء فوراً
            else:
                priority = "متوسطة"
                # تقدير عدد الأيام قبل الوصول للحد الأدنى (تقدير بسيط)
                days_to_action = round((part.Quantity - part.MinimumQuantity) * 2, 2)
            
            # حساب الكمية المقترح شراؤها
            suggested_quantity = max(part.MinimumQuantity * 2 - part.Quantity, 5)
            
            part_info = {
                "id": part.PartId,
                "name": part.PartName,
                "current_quantity": part.Quantity,
                "minimum_quantity": part.MinimumQuantity,
                "device_id": part.DeviceId,
                "device_name": FutureNeedsService._get_device_name(part.DeviceId),
                "lab_id": part.LaboratoryId,
                "unit": part.Unit,
                "cost": round(float(part.Cost), 2),
                "expiry_date": part.ExpiryDate.strftime('%Y-%m-%d') if part.ExpiryDate else None,
                "priority": priority,
                "reason": "منخفض المخزون",
                "stock_percentage": round(stock_percentage, 2),
                "days_to_action": days_to_action,
                "suggested_quantity": suggested_quantity,
                "total_cost_estimation": round(float(part.Cost) * suggested_quantity, 2)
            }
            all_parts_list.append(part_info)
        
        # 2. إضافة قطع الغيار التي تقارب انتهاء الصلاحية
        for part in expiring_parts:
            # تجنب التكرار
            if part.PartId not in [p["id"] for p in all_parts_list]:
                days_to_expiry = (part.ExpiryDate - today).days if part.ExpiryDate else 999
                
                # تحديد الأولوية بناءً على قرب انتهاء الصلاحية
                if days_to_expiry <= 15:
                    priority = "عالية"
                elif days_to_expiry <= 30:
                    priority = "متوسطة"
                else:
                    priority = "منخفضة"
                
                # الكمية المقترح شراؤها (لاستبدال المخزون الحالي)
                suggested_quantity = max(part.Quantity, part.MinimumQuantity)
                
                part_info = {
                    "id": part.PartId,
                    "name": part.PartName,
                    "current_quantity": part.Quantity,
                    "minimum_quantity": part.MinimumQuantity,
                    "device_id": part.DeviceId,
                    "device_name": FutureNeedsService._get_device_name(part.DeviceId),
                    "lab_id": part.LaboratoryId,
                    "unit": part.Unit,
                    "cost": round(float(part.Cost), 2),
                    "expiry_date": part.ExpiryDate.strftime('%Y-%m-%d') if part.ExpiryDate else None,
                    "priority": priority,
                    "reason": "قرب انتهاء الصلاحية",
                    "days_to_action": days_to_expiry,
                    "suggested_quantity": suggested_quantity,
                    "total_cost_estimation": round(float(part.Cost) * suggested_quantity, 2)
                }
                all_parts_list.append(part_info)
        
        # 3. إضافة قطع الغيار ذات معدل الاستهلاك العالي
        for part in high_consumption_parts:
            # تجنب التكرار
            if part.PartId not in [p["id"] for p in all_parts_list]:
                days_to_empty = getattr(part, 'estimated_days', 999)
                
                # تحديد الأولوية بناءً على سرعة نفاد المخزون
                if days_to_empty <= 15:
                    priority = "عالية"
                elif days_to_empty <= 30:
                    priority = "متوسطة"
                else:
                    priority = "منخفضة"
                
                # الكمية المقترح شراؤها بناءً على معدل الاستهلاك
                consumption_rate = getattr(part, 'consumption_rate', 0.1)
                suggested_quantity = max(round(consumption_rate * 60), part.MinimumQuantity)  # شراء ما يكفي لمدة شهرين
                
                part_info = {
                    "id": part.PartId,
                    "name": part.PartName,
                    "current_quantity": part.Quantity,
                    "minimum_quantity": part.MinimumQuantity,
                    "device_id": part.DeviceId,
                    "device_name": FutureNeedsService._get_device_name(part.DeviceId),
                    "lab_id": part.LaboratoryId,
                    "unit": part.Unit,
                    "cost": round(float(part.Cost), 2),
                    "expiry_date": part.ExpiryDate.strftime('%Y-%m-%d') if part.ExpiryDate else None,
                    "priority": priority,
                    "reason": "معدل استهلاك عالي",
                    "days_to_action": days_to_empty,
                    "consumption_rate": getattr(part, 'consumption_rate', 0),
                    "suggested_quantity": suggested_quantity,
                    "total_cost_estimation": round(float(part.Cost) * suggested_quantity, 2)
                }
                all_parts_list.append(part_info)
        
        # 4. إضافة قطع الغيار المطلوبة للصيانات القادمة
        for part in maintenance_related_parts:
            # تجنب التكرار
            if part.PartId not in [p["id"] for p in all_parts_list]:
                # تحديد حاجة الصيانة للقطع بناءً على المخزون الحالي
                if part.Quantity < part.MinimumQuantity:
                    priority = "عالية"
                    days_to_action = 0
                elif part.Quantity < part.MinimumQuantity * 1.5:
                    priority = "متوسطة"
                    days_to_action = 15
                else:
                    priority = "منخفضة"
                    days_to_action = 30
                
                # الكمية المقترح شراؤها (الحد الأدنى + إضافة للصيانة)
                suggested_quantity = max(part.MinimumQuantity - part.Quantity + 3, 3)
                
                part_info = {
                    "id": part.PartId,
                    "name": part.PartName,
                    "current_quantity": part.Quantity,
                    "minimum_quantity": part.MinimumQuantity,
                    "device_id": part.DeviceId,
                    "device_name": FutureNeedsService._get_device_name(part.DeviceId),
                    "lab_id": part.LaboratoryId,
                    "unit": part.Unit,
                    "cost": round(float(part.Cost), 2),
                    "expiry_date": part.ExpiryDate.strftime('%Y-%m-%d') if part.ExpiryDate else None,
                    "priority": priority,
                    "reason": "مطلوبة للصيانة القادمة",
                    "days_to_action": days_to_action,
                    "suggested_quantity": suggested_quantity,
                    "total_cost_estimation": round(float(part.Cost) * suggested_quantity, 2)
                }
                all_parts_list.append(part_info)
        
        # ترتيب القائمة النهائية حسب الأولوية ثم حسب عدد الأيام للإجراء
        priority_order = {"عالية": 0, "متوسطة": 1, "منخفضة": 2}
        final_sorted_list = sorted(all_parts_list, 
                                   key=lambda x: (priority_order.get(x["priority"], 3), x["days_to_action"]))
        
        # إحصائيات إجمالية
        total_parts_needed = len(final_sorted_list)
        total_estimated_cost = sum(item["total_cost_estimation"] for item in final_sorted_list)
        high_priority_count = sum(1 for item in final_sorted_list if item["priority"] == "عالية")
        
        # تجميع النتائج
        response = {
            "summary": {
                "total_parts_needed": total_parts_needed,
                "high_priority_count": high_priority_count,
                "total_estimated_cost": round(total_estimated_cost, 2),
                "date_generated": today.strftime('%Y-%m-%d')
            },
            "parts_to_purchase": final_sorted_list
        }
        
        return response
    
    @staticmethod
    def _get_device_name(device_id):
        """الحصول على اسم الجهاز من معرفه"""
        device = Devices.query.filter_by(Id=device_id).first()
        return device.Name if device else "غير معروف"
    
    @staticmethod
    def get_parts_by_priority(priority):
        """استرجاع قطع الغيار المطلوبة حسب الأولوية"""
        if priority not in ["عالية", "متوسطة", "منخفضة"]:
            return {"error": "الأولوية غير صالحة"}
        
        all_needs = FutureNeedsService.get_future_spare_parts_needs()
        filtered_parts = [part for part in all_needs["parts_to_purchase"] if part["priority"] == priority]
        
        # تحديث الملخص
        total_estimated_cost = sum(item["total_cost_estimation"] for item in filtered_parts)
        
        result = {
            "summary": {
                "total_parts_needed": len(filtered_parts),
                "high_priority_count": len(filtered_parts) if priority == "عالية" else 0,
                "total_estimated_cost": round(total_estimated_cost, 2),
                "date_generated": datetime.now().strftime('%Y-%m-%d'),
                "filter_applied": f"الأولوية: {priority}"
            },
            "parts_to_purchase": filtered_parts
        }
        
        return result
    
    @staticmethod
    def get_parts_by_reason(reason):
        """استرجاع قطع الغيار المطلوبة حسب السبب"""
        valid_reasons = ["منخفض المخزون", "قرب انتهاء الصلاحية", "معدل استهلاك عالي", "مطلوبة للصيانة القادمة"]
        
        if reason not in valid_reasons:
            return {"error": "السبب غير صالح"}
        
        all_needs = FutureNeedsService.get_future_spare_parts_needs()
        filtered_parts = [part for part in all_needs["parts_to_purchase"] if part["reason"] == reason]
        
        # تحديث الملخص
        total_estimated_cost = sum(item["total_cost_estimation"] for item in filtered_parts)
        high_priority_count = sum(1 for item in filtered_parts if item["priority"] == "عالية")
        
        result = {
            "summary": {
                "total_parts_needed": len(filtered_parts),
                "high_priority_count": high_priority_count,
                "total_estimated_cost": round(total_estimated_cost, 2),
                "date_generated": datetime.now().strftime('%Y-%m-%d'),
                "filter_applied": f"السبب: {reason}"
            },
            "parts_to_purchase": filtered_parts
        }
        
        return result 




class DevicesReplacementService:
    """خدمة لتقييم الأجهزة التي تحتاج إلى استبدال"""
    
    @staticmethod
    def get_devices_for_replacement():
        """الحصول على قائمة بالأجهزة التي قد تحتاج إلى استبدال مع تحليل لكل جهاز"""
        # الحصول على كل الأجهزة
        all_devices = Devices.query.all()
        
        results = []
        for device in all_devices:
            evaluation = DevicesReplacementService.evaluate_device_replacement(device)
            # لإظهار جميع الأجهزة التي تم تقييمها (سواء كانت بحاجة للاستبدال أو لا)
            # قم بتعليق الشرط التالي إذا كنت تريد رؤية كل الأجهزة
            if evaluation["should_retire"]:  # فقط الأجهزة التي تحتاج للاستبدال
                results.append(evaluation)
                
        # ترتيب النتائج حسب الأولوية
        priority_order = {"طارئة": 0, "عالية": 1, "متوسطه": 2, "ضعيفه": 3}
        results.sort(key=lambda x: priority_order.get(x["priority"], 4))
                
        return results
    
    @staticmethod
    def evaluate_device_replacement(device):
        """
        تقييم ما إذا كان الجهاز بحاجة إلى الاستبدال
        
        المعايير:
        1. العمر الافتراضي للجهاز (Lifespan) بالسنوات
        2. تكرار الصيانات في فترة قصيرة
        3. تكلفة الصيانة مقارنة بتكلفة الشراء
        """
        # البدء بافتراض عدم الحاجة للاستبدال
        result = {
            "device_id": device.Id,
            "device_name": device.Name,
            "device_serial": device.SerialNumber,
            "should_retire": False,
            "confidence": "ضعيفه",
            "reasons": [],
            "financial_analysis": {},
            "priority": "ضعيفه"
        }
        
        # المعيار 1: فحص العمر الافتراضي للجهاز بالسنوات
        lifespan_score = DevicesReplacementService._evaluate_by_lifespan(device)
        if lifespan_score:
            result["reasons"].append(lifespan_score["reason"])
            if lifespan_score["retire"]:
                result["should_retire"] = True
        
        # المعيار 2: تكرار الصيانات في فترة قصيرة
        maintenance_score = DevicesReplacementService._evaluate_by_maintenance_frequency(device)
        if maintenance_score:
            result["reasons"].append(maintenance_score["reason"])
            if maintenance_score["retire"]:
                result["should_retire"] = True
        
        # المعيار 3: تكلفة الصيانة مقارنة بتكلفة الشراء
        cost_score = DevicesReplacementService._evaluate_by_maintenance_cost(device)
        if cost_score:
            result["reasons"].append(cost_score["reason"])
            result["financial_analysis"] = cost_score["financial_analysis"]
            if cost_score["retire"]:
                result["should_retire"] = True
        
        # تحديد مستوى الثقة في التوصية
        confidence_scores = [s for s in [lifespan_score, maintenance_score, cost_score] if s]
        positive_scores = sum(1 for s in confidence_scores if s["retire"])
        
        if len(confidence_scores) > 0:
            confidence_ratio = positive_scores / len(confidence_scores)
            if confidence_ratio >= 0.7:
                result["confidence"] = "مرتفعه"
            elif confidence_ratio >= 0.4:
                result["confidence"] = "متوسطه"
            else:
                result["confidence"] = "ضعيفه"
        
        # تحديد مستوى الأولوية
        if result["should_retire"]:
            priorities = [s.get("priority", "ضعيفه") for s in confidence_scores if s]
            if "طارئة" in priorities:
                result["priority"] = "طارئة"
            elif "عالية" in priorities:
                result["priority"] = "عالية"
            elif "متوسطه" in priorities:
                result["priority"] = "متوسطه"
            else:
                result["priority"] = "ضعيفه"
        
        # إضافة نصائح وتوصيات
        result["recommendations"] = DevicesReplacementService._get_recommendations(device, result)
        
        return result
    
    @staticmethod
    def _evaluate_by_lifespan(device):
        """تقييم بناء على العمر الافتراضي للجهاز (بالسنوات)"""
        if not device.PurchaseDate or not device.Lifespan or device.Lifespan == 0:
            return None
        
        # حساب عمر الجهاز الحالي بالأيام
        device_age_days = (datetime.now() - device.PurchaseDate).days
        
        # تحويل العمر الافتراضي من سنوات إلى أيام
        lifespan_days = device.Lifespan * 365
        
        # حساب نسبة العمر المستهلك من العمر الافتراضي
        lifespan_percentage = (device_age_days / lifespan_days) * 100 if lifespan_days > 0 else 100
        
        # تقريب النسبة المئوية لأقرب رقمين عشريين
        lifespan_percentage = round(lifespan_percentage, 2)
        
        result = {
            "retire": False,
            "reason": "",
            "priority": "ضعيفه"
        }
        
        if lifespan_percentage >= 100:
            result["retire"] = True
            # تقريب النسبة الزائدة
            percentage_over = round(lifespan_percentage - 100, 2)
            result["reason"] = f"الجهاز تجاوز عمره الافتراضي ({device.Lifespan} سنوات) بنسبة {percentage_over}٪"
            result["priority"] = "طارئة"
        elif lifespan_percentage >= 85:  # تخفيف من 90% إلى 85%
            result["retire"] = True
            result["reason"] = f"الجهاز استهلك {lifespan_percentage}٪ من عمره الافتراضي البالغ {device.Lifespan} سنوات"
            result["priority"] = "عالية"
        elif lifespan_percentage >= 65:  # تخفيف من 70% إلى 65%
            result["retire"] = True
            result["reason"] = f"الجهاز استهلك {lifespan_percentage}٪ من عمره الافتراضي، وبدأ يقترب من نهاية عمره المتوقع"
            result["priority"] = "متوسطه"
        elif lifespan_percentage >= 50:  # إضافة شرط جديد للأجهزة التي استهلكت 50% من عمرها
            result["retire"] = False
            result["reason"] = f"الجهاز استهلك {lifespan_percentage}٪ من عمره الافتراضي، ويجب مراقبته"
            result["priority"] = "ضعيفه"
            return result
        else:
            return None
        
        return result
    
    @staticmethod
    def _evaluate_by_maintenance_frequency(device):
        """تقييم بناء على تكرار الصيانات في فترة قصيرة"""
        # الحصول على تاريخ صيانات الجهاز 
        six_months_ago = datetime.now() - timedelta(days=180)
        one_year_ago = datetime.now() - timedelta(days=365)
        
        # البحث عن صيانات الإصلاح خلال آخر 6 أشهر
        repair_maintenances = Maintenances.query.filter(
            Maintenances.DeviceId == device.Id,
            Maintenances.SchedulingAt > six_months_ago,
            Maintenances.Type == "إصلاح"
        ).all()
        
        # البحث عن صيانات الدورية خلال آخر سنة
        periodic_maintenances = Maintenances.query.filter(
            Maintenances.DeviceId == device.Id,
            Maintenances.SchedulingAt > one_year_ago,
            Maintenances.Type == "دورية"
        ).all()
        
        repair_count = len(repair_maintenances)
        periodic_count = len(periodic_maintenances)
        
        result = {
            "retire": False,
            "reason": "",
            "priority": "ضعيفه"
        }
        
        # تقييم معدل صيانات الإصلاح
        if repair_count >= 2:  # تخفيف من 3 إلى 2
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {repair_count} صيانات إصلاح خلال آخر 6 أشهر، وهو معدل مرتفع جداً"
            result["priority"] = "عالية"
            return result
        elif repair_count >= 1:  # تخفيف من 2 إلى 1
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {repair_count} صيانات إصلاح خلال آخر 6 أشهر، وهو معدل مرتفع"
            result["priority"] = "متوسطه"
            return result
        
        # تقييم معدل الصيانات الدورية
        if periodic_count >= 3:  # تخفيف من 4 إلى 3
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {periodic_count} صيانات دورية خلال آخر سنة، وهو معدل مرتفع جداً"
            result["priority"] = "عالية"
            return result
        elif periodic_count >= 2:  # تخفيف من 3 إلى 2
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {periodic_count} صيانات دورية خلال آخر سنة، وهو معدل مرتفع"
            result["priority"] = "متوسطه"
            return result
        
        # إذا كان هناك مزيج من الصيانات الإصلاحية والدورية
        combined_score = repair_count * 2 + periodic_count  # الصيانات الإصلاحية تؤثر بشكل أكبر
        if combined_score >= 3:  # تخفيف من 5 إلى 3
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {repair_count} صيانات إصلاح و {periodic_count} صيانات دورية، مما يشير إلى تدهور حالته"
            result["priority"] = "عالية"
            return result
        elif combined_score >= 2:  # تخفيف من 3 إلى 2
            result["retire"] = True
            result["reason"] = f"الجهاز خضع لـ {repair_count} صيانات إصلاح و {periodic_count} صيانات دورية، مما يشير إلى حاجته للمراقبة"
            result["priority"] = "متوسطه"
            return result
        elif combined_score >= 1:
            result["retire"] = False
            result["reason"] = f"الجهاز خضع لـ {repair_count} صيانات إصلاح و {periodic_count} صيانات دورية، وهو معدل يستدعي المراقبة"
            result["priority"] = "ضعيفه"
            return result
        
        return None
    
    @staticmethod
    def _evaluate_by_maintenance_cost(device):
        """تقييم بناء على تكلفة الصيانة مقارنة بتكلفة الشراء"""
        if device.PurchaseCost <= 0:
            return None
        
        # حساب إجمالي تكاليف الصيانة
        maintenance_costs = db.session.query(func.sum(Maintenances.Cost)).filter(
            Maintenances.DeviceId == device.Id
        ).scalar() or 0
        
        # حساب نسبة تكاليف الصيانة إلى تكلفة الشراء
        cost_ratio = (float(maintenance_costs) / float(device.PurchaseCost)) * 100
        
        yearly_cost_avg = 0
        device_age_years = (datetime.now() - device.PurchaseDate).days / 365 if device.PurchaseDate else 1
        if device_age_years > 0:
            yearly_cost_avg = float(maintenance_costs) / device_age_years
        
        # تقريب القيم العشرية إلى رقمين عشريين
        cost_ratio = round(cost_ratio, 2)
        yearly_cost_avg = round(yearly_cost_avg, 2)
        maintenance_costs_rounded = round(float(maintenance_costs), 2)
        purchase_cost_rounded = round(float(device.PurchaseCost), 2)
        
        result = {
            "retire": False,
            "reason": "",
            "priority": "ضعيفه",
            "financial_analysis": {
                "purchase_cost": purchase_cost_rounded,
                "total_maintenance_cost": maintenance_costs_rounded,
                "cost_ratio": cost_ratio,
                "yearly_maintenance_avg": yearly_cost_avg
            }
        }
        
        if cost_ratio >= 60:  # تخفيف من 70% إلى 60%
            result["retire"] = True
            result["reason"] = f"تكاليف الصيانة ({maintenance_costs_rounded:.2f}) تجاوزت 60% من تكلفة الشراء ({purchase_cost_rounded:.2f})"
            result["priority"] = "عالية"
        elif cost_ratio >= 40:  # تخفيف من 50% إلى 40%
            result["retire"] = True
            result["reason"] = f"تكاليف الصيانة ({maintenance_costs_rounded:.2f}) تجاوزت 40% من تكلفة الشراء ({purchase_cost_rounded:.2f})"
            result["priority"] = "متوسطه"
        elif cost_ratio >= 30:  # تخفيف من 40% إلى 30%
            result["retire"] = False
            result["reason"] = f"تكاليف الصيانة ({maintenance_costs_rounded:.2f}) تجاوزت 30% من تكلفة الشراء ({purchase_cost_rounded:.2f})"
            result["priority"] = "ضعيفه"
        else:
            return None
        
        return result
    
    @staticmethod
    def _get_recommendations(device, evaluation_result):
        """توليد نصائح وتوصيات بناء على نتائج التقييم"""
        recommendations = []
        
        if evaluation_result["should_retire"]:
            recommendations.append("يوصى باستبدال الجهاز بدلاً من إجراء المزيد من الصيانات")
            
            # تحقق من قطع الغيار المتبقية
            spare_parts = SpareParts.query.filter_by(DeviceId=device.Id).all()
            if spare_parts:
                total_parts_value = sum(float(part.Cost) * part.Quantity for part in spare_parts)
                # تقريب قيمة قطع الغيار لأقرب رقمين عشريين
                total_parts_value = round(total_parts_value, 2)
                recommendations.append(f"يرجى ملاحظة أن هناك قطع غيار متبقية للجهاز بقيمة إجمالية {total_parts_value:.2f}")
            
            # تحقق من ساعات التشغيل
            if device.TotalOperatingHours > 0:
                cost_per_hour = float(device.PurchaseCost) / device.TotalOperatingHours
                # تقريب تكلفة الساعة لأقرب رقمين عشريين
                cost_per_hour = round(cost_per_hour, 2)
                recommendations.append(f"متوسط تكلفة الساعة الواحدة من عمر الجهاز: {cost_per_hour:.2f}")
        else:
            recommendations.append("يمكن الاستمرار في صيانة الجهاز حيث أن تكلفة الصيانة لا تزال أقل من تكلفة الاستبدال")
        
        return recommendations
    



class DeviceSuggestionService:
    @staticmethod
    def get_device_suggestions(device_id):
        try:
            device = Devices.query.get(device_id)
            
            if not device:
                return False, "الجهاز غير موجود"
            
            excluded_statuses = [
                "قيد الصيانة", " قيد الصيانة", "قيد الصيانة ", " قيد الصيانة ",
                "غير متاح", " غير متاح", "غير متاح ", " غير متاح ",
                "في الصيانة", " في الصيانة", "في الصيانة ", " في الصيانة ",
                "فى الصيانة", " فى الصيانة", "فى الصيانة ", " فى الصيانة "
            ]
            
            similar_devices = Devices.query.filter(
                and_(
                    func.lower(Devices.CategoryName) == func.lower(device.CategoryName),
                    func.lower(Devices.JobDescription) == func.lower(device.JobDescription),
                    Devices.Id != device_id,
                    ~Devices.Status.in_(excluded_statuses)
                )
            ).all()
            
            if not similar_devices:
                return True, {"message": "لا توجد أجهزة مماثلة بنفس الوصف الوظيفي والفئة", "suggested_devices": []}
            
            name_similarity_matches = []
            other_similar_devices = []
            
            for d in similar_devices:
                name_similarity = difflib.SequenceMatcher(None, device.Name, d.Name).ratio()
                
                if name_similarity > 0.5:
                    name_similarity_matches.append({
                        "device": d,
                        "similarity": name_similarity
                    })
                else:
                    other_similar_devices.append(d)
            
            name_similarity_matches.sort(key=lambda x: x["similarity"], reverse=True)
            
            device_experiment_map = {}
            all_suggested_devices = []
            
            source_device_experiments = db.session.query(ExperimentDevices.ExperimentId).filter(
                ExperimentDevices.DeviceId == device_id
            ).all()
            
            source_experiment_ids = [exp[0] for exp in source_device_experiments]
            has_experiments = len(source_experiment_ids) > 0
            
            if has_experiments:
                for d in name_similarity_matches + other_similar_devices:
                    device_to_check = d["device"] if isinstance(d, dict) else d
                    device_experiments = db.session.query(ExperimentDevices.ExperimentId).filter(
                        ExperimentDevices.DeviceId == device_to_check.Id
                    ).all()
                    
                    device_experiment_ids = [exp[0] for exp in device_experiments]
                    common_experiments = [exp_id for exp_id in device_experiment_ids if exp_id in source_experiment_ids]
                    
                    if common_experiments:
                        device_experiment_map[device_to_check.Id] = common_experiments
            
            
            for match in name_similarity_matches:
                d = match["device"]
                device_info = {
                    "id": d.Id,
                    "name": d.Name,
                    "category": d.CategoryName,
                    "job_description": d.JobDescription,
                    "status": d.Status,
                    "use_recommendations": d.UseRecommendations,
                    "safety_recommendations": d.SafetyRecommendations,
                    "name_similarity": round(match["similarity"] * 100)  
                }
                
                if d.Id in device_experiment_map:
                    device_info["common_experiments"] = device_experiment_map[d.Id]
                
                all_suggested_devices.append(device_info)
            
            for d in other_similar_devices:
                device_info = {
                    "id": d.Id,
                    "name": d.Name,
                    "category": d.CategoryName,
                    "job_description": d.JobDescription,
                    "status": d.Status,
                    "use_recommendations": d.UseRecommendations,
                    "safety_recommendations": d.SafetyRecommendations
                }
                
                if d.Id in device_experiment_map:
                    device_info["common_experiments"] = device_experiment_map[d.Id]
                    all_suggested_devices.append(device_info)
            
            if has_experiments:
                for d in other_similar_devices:
                    if d.Id not in device_experiment_map:
                        all_suggested_devices.append({
                            "id": d.Id,
                            "name": d.Name,
                            "category": d.CategoryName,
                            "job_description": d.JobDescription,
                            "status": d.Status,
                            "use_recommendations": d.UseRecommendations,
                            "safety_recommendations": d.SafetyRecommendations
                        })
            
            if not all_suggested_devices:
                return True, {"message": "لا توجد أجهزة مماثلة مناسبة", "suggested_devices": []}
            
            return True, {"suggested_devices": all_suggested_devices}
            
        except Exception as e:
            return False, f"حدث خطأ أثناء البحث عن أجهزة مماثلة: {str(e)}"