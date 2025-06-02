import datetime
import os
import logging
from fit_tool.fit_file import FitFile
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.profile_type import FileType, Manufacturer, Sport, Event, EventType

logger = logging.getLogger(__name__)

class FitGenerator:
    """
    Generates Garmin FIT-Activity-Dateien aus Hevy-Trainingsdaten.
    """
    def generate_strength_activity_fit(self, hevy_workout_data: dict, output_dir: str = "temp_fit_files") -> str:
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        start_datetime = datetime.datetime.fromisoformat(hevy_workout_data['start_time'].replace("Z", "+00:00"))
        end_datetime = datetime.datetime.fromisoformat(hevy_workout_data['end_time'].replace("Z", "+00:00"))
        logger.debug(f"Parsed start_datetime: {start_datetime.isoformat()}")
        logger.debug(f"Parsed end_datetime: {end_datetime.isoformat()}")

        if start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(tzinfo=datetime.timezone.utc)
        if end_datetime.tzinfo is None:
            end_datetime = end_datetime.replace(tzinfo=datetime.timezone.utc)

        garmin_epoch = datetime.datetime(1989, 12, 31, tzinfo=datetime.timezone.utc)
        timestamp_fit_start = int((start_datetime - garmin_epoch).total_seconds())
        timestamp_fit_end = int((end_datetime - garmin_epoch).total_seconds())
        logger.debug(f"FIT timestamp start: {timestamp_fit_start}")
        logger.debug(f"FIT timestamp end: {timestamp_fit_end}")

        total_elapsed_time_seconds = (end_datetime - start_datetime).total_seconds()
        total_calories = int((total_elapsed_time_seconds / 60) * 6)
        logger.debug(f"Total workout duration: {total_elapsed_time_seconds} sec")
        logger.debug(f"Estimated calories burned: {total_calories}")

        builder = FitFileBuilder(auto_define=True)

        # FileIdMessage
        file_id_message = FileIdMessage()
        file_id_message.type = FileType.ACTIVITY
        file_id_message.manufacturer = Manufacturer.GARMIN
        file_id_message.product = 12345
        file_id_message.serial_number = 0x12345678
        file_id_message.time_created = round(start_datetime.timestamp() * 1000)
        builder.add(file_id_message)
        logger.debug("Added FileIdMessage")

        # SessionMessage
        session_message = SessionMessage()
        session_message.start_time = round(start_datetime.timestamp() * 1000)
        session_message.start_position_lat = 0
        session_message.start_position_long = 0
        session_message.total_elapsed_time = total_elapsed_time_seconds
        session_message.total_timer_time = total_elapsed_time_seconds

        import pprint
        pprint.pprint(list(Sport))

        #session_message.sport = Sport.STRENGTH_TRAINING
        session_message.sport = Sport.TRAINING
        session_message.sub_sport = 20 # Strength_Trainng
        session_message.total_calories = total_calories
        session_message.avg_heart_rate = 0
        session_message.max_heart_rate = 0
        session_message.total_distance = 0
        session_message.num_laps = 1
        session_message.timestamp = round(end_datetime.timestamp() * 1000)
        session_message.message_index = 0
        session_message.event = Event.SESSION
        session_message.event_type = EventType.STOP
        builder.add(session_message)
        logger.debug("Added SessionMessage")

        # Events: Start/Stop
        event_start_message = EventMessage()
        event_start_message.timestamp = round(start_datetime.timestamp() * 1000)
        event_start_message.event = Event.TIMER
        event_start_message.event_type = EventType.START
        builder.add(event_start_message)

        event_stop_message = EventMessage()
        event_stop_message.timestamp = round(end_datetime.timestamp() * 1000)
        event_stop_message.event = Event.TIMER
        event_stop_message.event_type = EventType.STOP
        builder.add(event_stop_message)
        logger.debug("Added EventMessages for start and stop")

        # RecordMessages
        current_timestamp_offset = 0
        exercises = hevy_workout_data.get('exercises', [])
        logger.debug(f"Found {len(exercises)} exercises in workout")

        for idx, exercise in enumerate(exercises):
            exercise_title = exercise.get("title", "Unnamed Exercise")
            logger.debug(f"Processing exercise {idx+1}: {exercise_title}")

            exercise_start_time = start_datetime + datetime.timedelta(seconds=current_timestamp_offset)
            #timestamp_fit_exercise_start = int((exercise_start_time - garmin_epoch).total_seconds())
            #logger.debug(f"Timestamp fit exercise start: {timestamp_fit_exercise_start} sec")

            record_message = RecordMessage()
            record_message.timestamp = round(exercise_start_time.timestamp() * 1000)
            record_message.distance = 0.0
            record_message.calories = 0
            record_message.heart_rate = 0
            record_message.power = 0
            builder.add(record_message)

            exercise_duration = sum(s.get('duration_seconds') or 60 for s in exercise.get('sets', []))
            logger.debug(f"Exercise duration estimated: {exercise_duration} sec")
            current_timestamp_offset += exercise_duration

        expected_end_timestamp = int((start_datetime + datetime.timedelta(seconds=current_timestamp_offset) - garmin_epoch).total_seconds())
        if not exercises or timestamp_fit_end > expected_end_timestamp:
            final_record_message = RecordMessage()
            final_record_message.timestamp = round(end_datetime.timestamp() * 1000)
            final_record_message.distance = 0.0
            final_record_message.calories = 0
            builder.add(final_record_message)
            logger.debug(f"Added final RecordMessage at timestamp {round(end_datetime.timestamp() * 1000)}")

        # LapMessage
        lap_message = LapMessage()
        lap_message.start_time = round(start_datetime.timestamp() * 1000)
        lap_message.timestamp = round(end_datetime.timestamp() * 1000)
        lap_message.total_elapsed_time = total_elapsed_time_seconds
        lap_message.total_timer_time = total_elapsed_time_seconds
        lap_message.total_distance = 0
        lap_message.total_calories = total_calories
        lap_message.avg_heart_rate = 0
        lap_message.max_heart_rate = 0
        lap_message.event = Event.LAP
        lap_message.event_type = EventType.STOP
        lap_message.message_index = 0
        builder.add(lap_message)
        logger.debug("Added LapMessage")

        # ActivityMessage
        activity_message = ActivityMessage()
        activity_message.timestamp = round(end_datetime.timestamp() * 1000)
        activity_message.total_timer_time = total_elapsed_time_seconds
        activity_message.num_sessions = 1
        activity_message.type = FileType.ACTIVITY
        activity_message.event = Event.ACTIVITY
        activity_message.event_type = EventType.STOP
        builder.add(activity_message)
        logger.debug("Added ActivityMessage")

        # Build and save FIT file
        fit_file = builder.build()
        file_name = f"hevy_strength_workout_{start_datetime.strftime('%Y%m%d_%H%M%S')}.fit"
        output_path = os.path.join(output_dir, file_name)
        fit_file.to_file(output_path)
        logger.info(f"FIT file generated: {output_path}")

        return output_path
