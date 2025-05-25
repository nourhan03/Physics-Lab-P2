from extensions import db
from datetime import datetime

class Users(db.Model):
    __tablename__ = 'Users'
    
    Id = db.Column(db.Integer, primary_key=True)
    UserType = db.Column(db.String, nullable=False)
    NationalId = db.Column(db.String, nullable=False)
    FullName = db.Column(db.String(100), nullable=False)
    PhoneNumber = db.Column(db.String(20), nullable=False)
    CreatedAt = db.Column(db.DateTime, nullable=False)
    Email = db.Column(db.String(100), nullable=False)
    LastLogin = db.Column(db.DateTime, nullable=True)
    ApplicationUserId = db.Column(db.String(450), nullable=False)
    
    # Relationships
    reservations = db.relationship('Reservations', backref='user', lazy=True)
    maintenances = db.relationship('Maintenances', backref='technician', lazy=True, foreign_keys='Maintenances.UserId')
    supervised_labs = db.relationship('Laboratories', backref='supervisor', lazy=True, foreign_keys='Laboratories.SupervisorId')
    alert_recipients = db.relationship('AlertRecipients', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.FullName}>'


class Devices(db.Model):
    __tablename__ = 'Devices'
    
    Id = db.Column(db.Integer, primary_key=True)
    SerialNumber = db.Column(db.String, nullable=False)
    Name = db.Column(db.String, nullable=False)
    CategoryName = db.Column(db.String, nullable=False)
    Status = db.Column(db.String, nullable=False)
    PurchaseDate = db.Column(db.DateTime, nullable=False)
    Lifespan = db.Column(db.Integer, nullable=False)
    Notes = db.Column(db.String, nullable=True)
    CurrentHour = db.Column(db.Integer, nullable=False)
    MaximumHour = db.Column(db.Integer, nullable=False)
    LastMaintenanceDate = db.Column(db.DateTime, nullable=True)
    NextMaintenanceDate = db.Column(db.DateTime, nullable=True)
    CalibrationInterval = db.Column(db.Integer, nullable=True)
    TotalOperatingHours = db.Column(db.Integer, nullable=False)
    PurchaseCost = db.Column(db.Numeric(10, 2), nullable=False)
    UseRecommendations = db.Column(db.String, nullable=False)
    SafetyRecommendations = db.Column(db.String, nullable=False)
    JobDescription = db.Column(db.String, nullable=False)
    
    # Relationships
    reservations = db.relationship('Reservations', backref='device', lazy=True)
    maintenances = db.relationship('Maintenances', backref='device', lazy=True)
    alerts = db.relationship('Alerts', backref='device', lazy=True)
    labs = db.relationship('Laboratories', secondary='DeviceLabs', backref='devices', lazy=True)
    experiments = db.relationship('Experiments', secondary='ExperimentDevices', backref='devices', lazy=True)
    spare_parts = db.relationship('SpareParts', backref='device', lazy=True)
    
    def __repr__(self):
        return f'<Device {self.Name}>'


class Laboratories(db.Model):
    __tablename__ = 'Laboratories'
    
    LabId = db.Column(db.Integer, primary_key=True)
    LabName = db.Column(db.String(100), nullable=False)
    Type = db.Column(db.String, nullable=False)
    Location = db.Column(db.String(100), nullable=False)
    Capacity = db.Column(db.Integer, nullable=True)
    SupervisorId = db.Column(db.Integer, db.ForeignKey('Users.Id'), nullable=True)
    Status = db.Column(db.String, nullable=False)
    TotalOperatingHours = db.Column(db.Integer, nullable=False)
    LastMaintenanceDate = db.Column(db.DateTime, nullable=True)
    OperatingCost = db.Column(db.Numeric(10, 2), nullable=False)
    UsageHours = db.Column(db.Integer, nullable=False)
    
    # Relationships
    experiments = db.relationship('Experiments', backref='laboratory', lazy=True)
    maintenances = db.relationship('Maintenances', backref='laboratory', lazy=True)
    reservations = db.relationship('Reservations', backref='laboratory', lazy=True)
    spare_parts = db.relationship('SpareParts', backref='laboratory', lazy=True)
    
    def __repr__(self):
        return f'<Laboratory {self.LabName}>'


class Experiments(db.Model):
    __tablename__ = 'Experiments'
    
    ExperimentId = db.Column(db.Integer, primary_key=True)
    ExperimentName = db.Column(db.String(100), nullable=False)
    Description = db.Column(db.String(255), nullable=False)
    LabId = db.Column(db.Integer, db.ForeignKey('Laboratories.LabId'), nullable=True)
    CompletedCount = db.Column(db.Integer, nullable=False)
    Type = db.Column(db.String, nullable=False)
    
    # Relationships
    reservations = db.relationship('Reservations', backref='experiment', lazy=True)
    
    def __repr__(self):
        return f'<Experiment {self.ExperimentName}>'


class Reservations(db.Model):
    __tablename__ = 'Reservations'
    
    Id = db.Column(db.Integer, primary_key=True)
    Date = db.Column(db.Date, nullable=False)
    StartTime = db.Column(db.Time, nullable=False)
    EndTime = db.Column(db.Time, nullable=False)
    Purpose = db.Column(db.Unicode, nullable=True)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id'), nullable=False)
    UserId = db.Column(db.Integer, db.ForeignKey('Users.Id'), nullable=False)
    ExperimentId = db.Column(db.Integer, db.ForeignKey('Experiments.ExperimentId'), nullable=True)
    IsAllowed = db.Column(db.Boolean, nullable=False)
    LabId = db.Column(db.Integer, db.ForeignKey('Laboratories.LabId'), nullable=True)
    
    def __repr__(self):
        return f'<Reservation {self.Id}>'


class Maintenances(db.Model):
    __tablename__ = 'Maintenances'
    
    Id = db.Column(db.Integer, primary_key=True)
    Priority = db.Column(db.String, nullable=True)
    Status = db.Column(db.String, nullable=False)
    Type = db.Column(db.String, nullable=False)
    SchedulingAt = db.Column(db.DateTime, nullable=False)
    StartAt = db.Column(db.DateTime, nullable=True)
    EndAt = db.Column(db.DateTime, nullable=True)
    Cost = db.Column(db.Numeric(10, 2), nullable=False)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id'), nullable=True)
    Notes = db.Column(db.String, nullable=True)
    Reason = db.Column(db.String, nullable=False)
    UserId = db.Column(db.Integer, db.ForeignKey('Users.Id'), nullable=False)
    LabId = db.Column(db.Integer, db.ForeignKey('Laboratories.LabId'), nullable=True)
    
    def __repr__(self):
        return f'<Maintenance {self.Id}>'


class Alerts(db.Model):
    __tablename__ = 'Alerts'
    
    Id = db.Column(db.Integer, primary_key=True)
    Type = db.Column(db.String, nullable=False)
    Level = db.Column(db.String, nullable=False)
    Title = db.Column(db.String, nullable=False)
    Message = db.Column(db.String, nullable=False)
    CreatedAt = db.Column(db.DateTime, nullable=False)
    ExpiresAt = db.Column(db.DateTime, nullable=False)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id'), nullable=False)
    
    # Relationships
    recipients = db.relationship('AlertRecipients', backref='alert', lazy=True)
    
    def __repr__(self):
        return f'<Alert {self.Title}>'


class AlertRecipients(db.Model):
    __tablename__ = 'AlertRecipients'
    
    UserId = db.Column(db.Integer, db.ForeignKey('Users.Id'), primary_key=True)
    AlertId = db.Column(db.Integer, db.ForeignKey('Alerts.Id'), primary_key=True)
    Id = db.Column(db.Integer, nullable=False)
    
    def __repr__(self):
        return f'<AlertRecipient User {self.UserId} Alert {self.AlertId}>'


class SpareParts(db.Model):
    __tablename__ = 'SpareParts'
    
    PartId = db.Column(db.Integer, primary_key=True)
    PartName = db.Column(db.String(100), nullable=False)
    Type = db.Column(db.String, nullable=False)
    Quantity = db.Column(db.Integer, nullable=False)
    MinimumQuantity = db.Column(db.Integer, nullable=False)
    LastRestockDate = db.Column(db.DateTime, nullable=True)
    ExpiryDate = db.Column(db.DateTime, nullable=True)
    Unit = db.Column(db.String(20), nullable=False)
    Cost = db.Column(db.Numeric(10, 2), nullable=False)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id'), nullable=False)
    LaboratoryId = db.Column(db.Integer, db.ForeignKey('Laboratories.LabId'), nullable=False)
    Notes = db.Column(db.String, nullable=True)
    
    def __repr__(self):
        return f'<SparePart {self.PartName}>'


# Association Tables
class DeviceLabs(db.Model):
    __tablename__ = 'DeviceLabs'
    
    Id = db.Column(db.Integer, primary_key=True)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id', ondelete='CASCADE'), nullable=False)
    LabId = db.Column(db.Integer, db.ForeignKey('Laboratories.LabId', ondelete='CASCADE'), nullable=False)


class ExperimentDevices(db.Model):
    __tablename__ = 'ExperimentDevices'
    
    Id = db.Column(db.Integer, primary_key=True)
    ExperimentId = db.Column(db.Integer, db.ForeignKey('Experiments.ExperimentId', ondelete='CASCADE'), nullable=False)
    DeviceId = db.Column(db.Integer, db.ForeignKey('Devices.Id', ondelete='CASCADE'), nullable=False) 