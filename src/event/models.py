import ast
import logging
import operator
import uuid
from functools import reduce

from device.models import Command, Device
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule
from utils.time_and_space import is_number

User = get_user_model()
logger = logging.getLogger('django')

# Create your models here.

event_triggering = (
    ('Data', 'Data triggered event.'),
    ('Time', 'Time triggered event.'),
)

ALARM_OPERATOR_EQ = 'eq'
ALARM_OPERATOR_NEQ = 'neq'
ALARM_OPERATOR_GT = 'gt'
ALARM_OPERATOR_GTE = 'gte'
ALARM_OPERATOR_LT = 'lt'
ALARM_OPERATOR_LTE = 'lte'
ALARM_OPERATOR_CONTAINS = 'contains'

ALARM_OPERATOR_CHOICES = (
    (ALARM_OPERATOR_EQ, 'Equals'),
    (ALARM_OPERATOR_NEQ, 'Not Equals'),
    (ALARM_OPERATOR_GT, 'Greater Than'),
    (ALARM_OPERATOR_GTE, 'Greater Than or Equals'),
    (ALARM_OPERATOR_LT, 'Less Than'),
    (ALARM_OPERATOR_LTE, 'Less Than or Equals'),
    (ALARM_OPERATOR_CONTAINS, 'Contains'),
)

ALARM_CHANNEL_IN_APP = 'in_app'
ALARM_CHANNEL_TELEGRAM = 'telegram'
ALARM_CHANNEL_EMAIL = 'email'


class EventType(models.Model):
    """
        Event Type model.
    """
    ALARM_OPERATOR_EQ = ALARM_OPERATOR_EQ
    ALARM_OPERATOR_NEQ = ALARM_OPERATOR_NEQ
    ALARM_OPERATOR_GT = ALARM_OPERATOR_GT
    ALARM_OPERATOR_GTE = ALARM_OPERATOR_GTE
    ALARM_OPERATOR_LT = ALARM_OPERATOR_LT
    ALARM_OPERATOR_LTE = ALARM_OPERATOR_LTE
    ALARM_OPERATOR_CONTAINS = ALARM_OPERATOR_CONTAINS
    ALARM_OPERATOR_CHOICES = ALARM_OPERATOR_CHOICES

    ALARM_CHANNEL_IN_APP = ALARM_CHANNEL_IN_APP
    ALARM_CHANNEL_TELEGRAM = ALARM_CHANNEL_TELEGRAM
    ALARM_CHANNEL_EMAIL = ALARM_CHANNEL_EMAIL

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, help_text="Event type name")
    description = models.TextField(help_text='Description')
    trigger_type = models.CharField(max_length=20, choices=event_triggering)
    equation = models.TextField(max_length=255, help_text='Trigger equation', null=True, blank=True)
    is_alarm_type = models.BooleanField(default=False)
    status_key = models.CharField(max_length=255, null=True, blank=True)
    operator = models.CharField(max_length=16, choices=ALARM_OPERATOR_CHOICES, null=True, blank=True)
    target_value = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Event types'

    def __str__(self):
        return self.name


class DeviceEvent(models.Model):
    """
        Device events model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    typ = models.ForeignKey(EventType, on_delete=models.CASCADE)
    device = models.ForeignKey(Device, related_name='events', blank=True, null=True, on_delete=models.CASCADE)
    user = models.ForeignKey(User, related_name='events', blank=True, null=True, on_delete=models.CASCADE)
    equation_threshold = models.CharField(max_length=255, help_text='Threshold value for the event equations', null=True, blank=True)
    schedule = models.ForeignKey(CrontabSchedule, null=True, blank=True, on_delete=models.CASCADE)
    last_trigger_time = models.DateTimeField(null=True, blank=True)
    last_evaluation_match = models.BooleanField(default=False)
    actions_config = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Device events'

    def __str__(self):
        return "{dev} - {typ}".format(dev=self.device.ip_address if self.device else self.user.user.username, typ=self.typ.name)

    def _safe_evaluate_expression(self, expression, context_variables):
        """
        Safely evaluate a mathematical/comparison expression without using eval().
        Supports: +, -, *, /, >, <, >=, <=, ==, !=, and, or parentheses
        """
        try:
            # Parse expression into AST
            node = ast.parse(expression, mode='eval')
            
            # Define allowed operations
            allowed_ops = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Gt: operator.gt,
                ast.Lt: operator.lt,
                ast.GtE: operator.ge,
                ast.LtE: operator.le,
                ast.Eq: operator.eq,
                ast.NotEq: operator.ne,
                ast.And: operator.and_,
                ast.Or: operator.or_,
            }
            
            def _eval_node(node):
                if isinstance(node, ast.Expression):
                    return _eval_node(node.body)
                elif isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.Num):  # Python 3.7 compatibility
                    return node.n
                elif isinstance(node, ast.Name):
                    if node.id in context_variables:
                        return context_variables[node.id]
                    raise ValueError(f"Undefined variable: {node.id}")
                elif isinstance(node, ast.BinOp):
                    left = _eval_node(node.left)
                    right = _eval_node(node.right)
                    op = allowed_ops.get(type(node.op))
                    if op is None:
                        raise ValueError(f"Operation not allowed: {type(node.op).__name__}")
                    return op(left, right)
                elif isinstance(node, ast.UnaryOp):
                    if isinstance(node.op, (ast.UAdd, ast.USub)):
                        val = _eval_node(node.operand)
                        return -val if isinstance(node.op, ast.USub) else val
                    raise ValueError(f"Operation not allowed: {type(node.op).__name__}")
                elif isinstance(node, ast.Compare):
                    left = _eval_node(node.left)
                    for op, comparator in zip(node.ops, node.comparators):
                        right = _eval_node(comparator)
                        op_func = allowed_ops.get(type(op))
                        if op_func is None:
                            raise ValueError(f"Operation not allowed: {type(op).__name__}")
                        if not op_func(left, right):
                            return False
                        left = right
                    return True
                elif isinstance(node, ast.BoolOp):
                    op = allowed_ops.get(type(node.op))
                    if op is None:
                        raise ValueError(f"Operation not allowed: {type(node.op).__name__}")
                    if isinstance(node.op, ast.And):
                        return all(_eval_node(value) for value in node.values)
                    elif isinstance(node.op, ast.Or):
                        return any(_eval_node(value) for value in node.values)
                else:
                    raise ValueError(f"Expression type not allowed: {type(node).__name__}")
            
            return _eval_node(node.body)
        except Exception as e:
            logger.error(f"Error evaluating expression '{expression}': {str(e)}")
            raise ValueError(f"Invalid expression: {str(e)}")

    def eval_equation(self, data=None):
        event_typ = self.typ
        equation = event_typ.equation
        if equation == "":
            return True
        data_members = [attr for attr in dir(data) if not callable(attr) and not attr.startswith("__")]
        logger.info("Equation is {}".format(equation))
        time_now = timezone.now()
        context_variables = {
            "time_now": time_now
        }
        for data_member in data_members:
            try:
                data_member_val = getattr(data, data_member, None)
                context_variables[data_member] = data_member_val
                if f"{data_member}_val" in equation:
                    equation = equation.replace("{}_val".format(data_member), str(data_member_val))
            except Exception as e:
                logger.warning(f"Could not access data member {data_member}: {str(e)}")

        logger.info("Transformed Equation is {}".format(equation))
        try:
            result = self._safe_evaluate_expression(equation, context_variables)
        except Exception as e:
            logger.error(f"Failed to evaluate equation '{equation}': {str(e)}")
            return False
        
        logger.info("Result of the equation is {}".format(result))

        result_is_number, result = is_number(result)
        threshold_is_number, threshold = is_number(self.equation_threshold)
        if result_is_number and threshold_is_number:
            if result - threshold > 0:
                return True
        elif threshold is None:
            return True
        elif result is not None:
            target_type = type(result)
            logger.critical("data type of result {} is {}".format(result, target_type))
            # Convert the threshold into data type of result
            threshold = target_type(threshold)
            if result == threshold:
                return True
        return False

class Action(models.Model):
    """
        Action model
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    device_event = models.ForeignKey(DeviceEvent, on_delete=models.CASCADE)
    device_command = models.CharField(max_length=255, blank=True, null=True)

    task = models.CharField(
        max_length=200,
        blank=True, null=True,
        verbose_name='Task Name',
        help_text=('The Name of the Celery Task that Should be Run.  '
                    '(Example: "proj.tasks.import_contacts")'),
    )
    
    args = models.JSONField(
        blank=True, null=True,
        verbose_name=('Positional Arguments'),
        help_text=(
            'JSON encoded positional arguments '
            '(Example: ["arg1", "arg2"])'),
    )
    kwargs = models.JSONField(
        blank=True, null=True,
        verbose_name=('Keyword Arguments'),
        help_text=(
            'JSON encoded keyword arguments '
            '(Example: {"argument": "value"})'),
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)
    
    class Meta:
        verbose_name_plural = 'Actions'

    def __str__(self):
        return "{name} - {dev_event}".format(name=self.name, dev_event=self.device_event)


class EventHistory(models.Model):
    """
        Event history model.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_event = models.ForeignKey(DeviceEvent, on_delete=models.CASCADE)
    trigger_time = models.DateTimeField(auto_now_add=True)
    
    action = models.ForeignKey(Action, blank=True, null=True, on_delete=models.CASCADE)
    result = models.JSONField(blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Events history'

    def __str__(self):
        return "{dev} - {typ} - {time}".format(
            dev=self.device_event.device.ip_address,
            typ=self.device_event.typ.name,
            time=self.trigger_time.strftime("%d-%m-%Y %H:%M:%S")
        )
