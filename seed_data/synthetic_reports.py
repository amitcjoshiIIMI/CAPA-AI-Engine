import json
import boto3
from datetime import datetime
from decimal import Decimal

from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

SEED_REPORTS = {
    "Crazing": {
        "failure_mode": "Crazing",
        "five_whys": {
            "why_1": "Why did crazing appear? Surface stress exceeded material tolerance.",
            "why_2": "Why did stress exceed tolerance? Cooling rate was too rapid during manufacturing.",
            "why_3": "Why was cooling rate rapid? Temperature controller setpoint was misconfigured.",
            "why_4": "Why was setpoint wrong? Recent maintenance reset default parameters.",
            "why_5": "Why weren't parameters verified? Post-maintenance checklist was incomplete."
        },
        "fishbone": {
            "man": "Operator did not verify controller settings after maintenance",
            "machine": "Temperature controller lacks parameter lock feature",
            "material": "Steel grade has low thermal shock resistance",
            "method": "Post-maintenance verification procedure is inadequate",
            "measurement": "No real-time stress monitoring during cool-down phase",
            "environment": "Ambient temperature fluctuations affect cooling uniformity"
        },
        "8d_report": {
            "d1_team": "Quality Engineer, Maintenance Supervisor, Process Engineer",
            "d2_problem": "Crazing defects observed on 12% of production batch due to thermal stress",
            "d3_interim": "Manual inspection of all units; rework cracked surfaces",
            "d4_root_cause": "Temperature controller misconfiguration post-maintenance",
            "d5_corrective": "Implement parameter lock-out on temperature controllers; update maintenance SOP",
            "d6_implementation": "Deploy firmware update to 8 controllers; train 15 operators on new checklist",
            "d7_prevention": "Add automated alert for parameter deviation; quarterly audit of control settings",
            "d8_recognition": "Acknowledge maintenance team for identifying gap in verification process"
        }
    },
    "Inclusion": {
        "failure_mode": "Inclusion",
        "five_whys": {
            "why_1": "Why are inclusions present? Foreign particles embedded in material during casting.",
            "why_2": "Why were particles in the melt? Furnace refractory lining is degrading.",
            "why_3": "Why is lining degrading? Exceeded recommended service life by 400 hours.",
            "why_4": "Why wasn't it replaced? Preventive maintenance schedule was not updated after production increase.",
            "why_5": "Why wasn't schedule updated? No formal review process for PM intervals vs. production changes."
        },
        "fishbone": {
            "man": "Furnace operator missed visual inspection signs of refractory wear",
            "machine": "Furnace lining material has shorter lifespan than expected",
            "material": "Raw material supplier changed slag composition without notification",
            "method": "PM schedule is static and not linked to actual run hours",
            "measurement": "No online particle detection in molten metal",
            "environment": "High humidity accelerates refractory chemical degradation"
        },
        "8d_report": {
            "d1_team": "Metallurgist, Furnace Operator, Supply Chain Manager",
            "d2_problem": "Non-metallic inclusions found in 8% of rolled products causing rejection",
            "d3_interim": "Source material from backup furnace; 100% ultrasonic inspection of affected batch",
            "d4_root_cause": "Degraded furnace refractory due to exceeded maintenance interval",
            "d5_corrective": "Replace furnace lining; implement run-hour-based PM trigger",
            "d6_implementation": "Install new refractory (72-hour downtime); deploy CMMS automation for dynamic scheduling",
            "d7_prevention": "Monthly refractory thickness measurement; supplier material certification requirement",
            "d8_recognition": "Commend quality lab for early detection through improved sampling rate"
        }
    },
    "Patches": {
        "failure_mode": "Patches",
        "five_whys": {
            "why_1": "Why do patches appear? Uneven coating thickness during galvanization.",
            "why_2": "Why is coating uneven? Zinc bath temperature has 15°C variation across width.",
            "why_3": "Why does temperature vary? Induction heater coils have uneven power distribution.",
            "why_4": "Why is power distribution uneven? Two of twelve coils have 30% resistance degradation.",
            "why_5": "Why weren't failed coils detected? Predictive maintenance sensors were not installed on heaters."
        },
        "fishbone": {
            "man": "Line operator unaware of optimal bath temperature range",
            "machine": "Induction heater design lacks redundancy for coil failures",
            "material": "Zinc alloy purity variation affects surface tension",
            "method": "Temperature monitoring is single-point, not zonal",
            "measurement": "Coating thickness gauge samples only 5% of surface area",
            "environment": "Drafts from facility HVAC create localized cooling"
        },
        "8d_report": {
            "d1_team": "Coating Specialist, Electrical Engineer, Production Manager",
            "d2_problem": "Patchy zinc coating on 18% of strip steel causing customer complaints",
            "d3_interim": "Reduce line speed by 20%; increase sampling to 15% of area",
            "d4_root_cause": "Failed induction coils causing non-uniform bath temperature",
            "d5_corrective": "Replace degraded coils; install multi-zone temperature control",
            "d6_implementation": "Coil replacement during planned shutdown; deploy 12-point thermocouple array",
            "d7_prevention": "Quarterly infrared scan of heater assembly; automated temperature variance alarms",
            "d8_recognition": "Recognize maintenance electrician for identifying coil resistance anomaly"
        }
    },
    "Pitted_Surface": {
        "failure_mode": "Pitted_Surface",
        "five_whys": {
            "why_1": "Why is surface pitted? Localized corrosion during acid pickling process.",
            "why_2": "Why did corrosion occur? Acid concentration exceeded specification (22% vs. 18%).",
            "why_3": "Why was concentration high? Automated dosing pump failed in open position.",
            "why_4": "Why did pump fail? Mechanical seal degraded due to chemical exposure.",
            "why_5": "Why wasn't degradation detected? Pump health monitoring was not implemented."
        },
        "fishbone": {
            "man": "Pickling operator did not perform hourly pH verification",
            "machine": "Dosing pump lacks fail-safe closed position",
            "material": "Acid supplier delivered batch with 2% higher concentration than ordered",
            "method": "Acid concentration control relies on single pump with no backup",
            "measurement": "Online pH sensor has ±0.5 accuracy, insufficient for tight control",
            "environment": "Tank ventilation inadequate, causing acid fume concentration and accelerated corrosion"
        },
        "8d_report": {
            "d1_team": "Chemical Engineer, Process Technician, EHS Coordinator",
            "d2_problem": "Surface pitting on 22% of pickled coils due to acid over-concentration",
            "d3_interim": "Halt pickling line; manually dilute acid bath to specification; rework affected material",
            "d4_root_cause": "Dosing pump mechanical failure allowing acid over-injection",
            "d5_corrective": "Install redundant dosing pump with interlock; replace failed pump seal",
            "d6_implementation": "Deploy backup pump system; upgrade to high-precision pH sensor (±0.1)",
            "d7_prevention": "Weekly pump seal inspection; automated concentration alarm at ±1% deviation",
            "d8_recognition": "Acknowledge EHS team for immediate containment preventing personnel exposure"
        }
    },
    "Rolled-in_Scale": {
        "failure_mode": "Rolled-in_Scale",
        "five_whys": {
            "why_1": "Why is scale rolled into surface? Descaling water pressure was insufficient.",
            "why_2": "Why was pressure low? High-pressure pump motor tripped offline.",
            "why_3": "Why did motor trip? Electrical overload due to clogged pump intake filter.",
            "why_4": "Why was filter clogged? Cooling water recirculation system has excessive sediment.",
            "why_5": "Why is there sediment? Cooling tower water treatment was delayed by 3 weeks."
        },
        "fishbone": {
            "man": "Rolling mill operator did not notice pressure gauge drop",
            "machine": "Descaling pump has no automatic pressure regulation",
            "material": "Incoming hot-rolled scale thickness exceeded typical range",
            "method": "Water treatment schedule is calendar-based, not condition-based",
            "measurement": "Pressure gauge is analog with poor visibility from control station",
            "environment": "High ambient dust levels increase cooling tower sediment load"
        },
        "8d_report": {
            "d1_team": "Rolling Mill Supervisor, Maintenance Lead, Water Treatment Specialist",
            "d2_problem": "Rolled-in scale defects on 14% of cold-rolled coils causing surface quality failures",
            "d3_interim": "Manual descaling using wire brush; secondary inspection gate installed",
            "d4_root_cause": "Descaling pump pressure loss due to filter clogging from untreated cooling water",
            "d5_corrective": "Clean pump filter; perform emergency water treatment; install differential pressure sensor",
            "d6_implementation": "Deploy automated filter monitoring; establish condition-based water treatment",
            "d7_prevention": "Bi-weekly filter inspection; upgrade to digital pressure display at HMI",
            "d8_recognition": "Commend operator for quickly identifying correlation between gauge reading and defect rate"
        }
    },
    "Scratches": {
        "failure_mode": "Scratches",
        "five_whys": {
            "why_1": "Why are scratches appearing? Entry guide roller has surface damage.",
            "why_2": "Why is roller damaged? Foreign metal debris became embedded during operation.",
            "why_3": "Why was debris present? Upstream shearing operation generated metal chips.",
            "why_4": "Why did chips reach the roller? Chip evacuation system was not functioning.",
            "why_5": "Why wasn't evacuation system working? Vacuum blower belt slipped off pulley due to wear."
        },
        "fishbone": {
            "man": "Line attendant did not perform pre-shift roller inspection",
            "machine": "Guide roller material (chrome-plated steel) is susceptible to embedding",
            "material": "Sheared edge quality deteriorated, producing more chips than normal",
            "method": "No mandatory chip evacuation verification before line startup",
            "measurement": "No automated debris detection system between shear and rolling mill",
            "environment": "Magnetic chip buildup on floor increases airborne particle concentration"
        },
        "8d_report": {
            "d1_team": "Mill Engineer, Roller Technician, Shear Operator",
            "d2_problem": "Linear scratches on 28% of finished coils due to damaged guide roller",
            "d3_interim": "Emergency roller replacement; install temporary magnetic chip collector",
            "d4_root_cause": "Chip evacuation system failure allowed debris to damage roller surface",
            "d5_corrective": "Replace vacuum blower belt; upgrade to ceramic-coated guide rollers",
            "d6_implementation": "Install belt tension monitoring; deploy 6 ceramic rollers (lead time: 4 weeks)",
            "d7_prevention": "Daily chip evacuation system test; automated interlock preventing startup if vacuum <80%",
            "d8_recognition": "Recognize maintenance planner for sourcing expedited ceramic roller delivery"
        }
    }
}


def upload_seed_reports():
    """Upload synthetic reports to DynamoDB and S3"""
    dynamodb = boto3.resource('dynamodb')
    s3 = boto3.client('s3')
    
    table = dynamodb.Table('CapaStorageStack-ReportsTable282F2283-8FX9IECXXFMR')
    bucket = 'capastoragestack-reportsbucket4e7c5994-rxmlfbl4bfzb'
    
    for failure_mode, report_data in SEED_REPORTS.items():
        report_id = f"SEED_{failure_mode}_{datetime.now().strftime('%Y%m%d')}"
        
        # Add metadata
        full_report = {
            "report_id": report_id,
            "created_at": datetime.now().isoformat(),
            "image_id": f"synthetic_{failure_mode.lower()}",
            "confidence": Decimal("1.0"),
            "is_seed": True,
            **report_data
        }
        
        # DynamoDB
        table.put_item(Item=full_report)
        
        # S3
        s3.put_object(
            Bucket=bucket,
            Key=f"reports/{report_id}.json",
            Body=json.dumps(full_report, indent=2, cls=DecimalEncoder)
        )
        
        print(f"✓ Uploaded {report_id}")


if __name__ == "__main__":
    upload_seed_reports()