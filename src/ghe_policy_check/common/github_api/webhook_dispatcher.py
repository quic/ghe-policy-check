# Copyright (c) 2022, Qualcomm Innovation Center, Inc. All rights reserved.
# SPDX-License-Identifier: BSD-3-Clause

import hmac
import logging
from hashlib import sha1
from typing import Any, Callable, Dict, Optional, Union

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseServerError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_204_NO_CONTENT, HTTP_501_NOT_IMPLEMENTED

logger = logging.getLogger(__name__)


class NoHeaderSignatureException(Exception):
    pass


class OperationNotSupportedException(Exception):
    pass


class InvalidSignature(Exception):
    pass


class UnhandledEventException(Exception):
    pass


class UnhandledActionException(Exception):
    pass


WebhookHandler = Callable[[Any], Any]


def dispatch_webhook(request: Request) -> HttpResponse:
    """
    Dispatches an incoming webhook to the function that has been registered
    to handle it, if one has been.

    :param request: Incoming webhook request
    :return: HTTPResponse based on how the request was handled.
    :rtype: HTTPResponse
    """
    logger.info("Received webhook request")
    body = request.body
    event = request.headers["X-GitHub-Event"]
    action = request.data.get("action")
    dispatcher = WebhookDispatcher(settings.GITHUB_WEBHOOK_KEY)
    try:
        response: Response = dispatcher.dispatch(
            request=request,
            event=event,
            action=action,
            signature=request.META.get("HTTP_X_HUB_SIGNATURE"),
            body=body,
        )
    except UnhandledEventException:
        return HttpResponse(status=HTTP_204_NO_CONTENT)
    except UnhandledActionException:
        return HttpResponse(status=HTTP_204_NO_CONTENT)
    except OperationNotSupportedException:
        return HttpResponseServerError("Operation not supported.", status=HTTP_501_NOT_IMPLEMENTED)
    except InvalidSignature:
        return HttpResponseForbidden("Permission denied.")

    logger.info("Handling event: '%s.%s'", event, action)
    return response


class WebhookDispatcher:
    """
    Dispatcher class register functions to webhook types and to keep track
    of those registered functions.
    """

    registry: Dict[str, Union[WebhookHandler, Dict[str, WebhookHandler]]] = {}

    def __init__(self, secret: str):
        self.secret = secret

    def secure_github_request(self, signature: str, body: bytes) -> None:
        """
        Validates a provided signature matches what would be expected
        and raises an :class:`InvalidSignature` if it does not match

        :param signature: The provided signature from the request
        :param body: The body of the request used in validated the signature
        """
        if signature is None:
            raise InvalidSignature

        sha_name, signature_body = signature.split("=")

        if sha_name != "sha1":
            raise OperationNotSupportedException
        mac = hmac.new(self.secret.encode(), msg=body, digestmod=sha1)
        if not hmac.compare_digest(mac.hexdigest(), signature_body):
            raise InvalidSignature

    @classmethod
    def register(
        cls, event: str, action: Optional[str] = None
    ) -> Callable[[WebhookHandler], WebhookHandler]:
        """
        Registers a decorated function to handle the action specified in the decorator.
        If no action is provided the function will be registered to handle all
        actions of that event type.s

        :param event: The GitHub event to associate the action with
        :param action: An optional specific GitHub action to register the function with
        """

        def decorator(handler: Callable[[Any], Any]) -> Callable[[Any], Any]:
            if action:
                event_registry = cls.registry.setdefault(event.lower(), {})
                if callable(event_registry):
                    raise ValueError(
                        "Trying to register action handler to event with existing event handler"
                    )

                event_registry[action.lower()] = handler
            else:
                cls.registry[event] = handler
            return handler

        return decorator

    def dispatch(self, request: Any, event: str, action: str, signature: str, body: bytes) -> Any:
        """
        Dispatches a webhook to its registered function, verifying the signature
        of the request

        :param request: The incoming :class:`HTTPRequest`
        :param event: The name of the GitHub event
        :param action: The name of the GitHub action
        :param signature: The signature of the webhook
        :param body: The body of the incoming request
        :return: Passes on the return value from the registered function
        :rtype: Any
        """
        self.secure_github_request(signature, body)

        event_handler = self.registry.get(event.lower())

        if not event_handler:
            raise UnhandledActionException(f"Unhandled event: {event}")

        # Allow a method to handle event
        if callable(event_handler):
            return event_handler(request)
        if not action:
            raise UnhandledActionException(f"Unhandled event: {event}")

        action_handler = event_handler.get(action.lower())
        if not action_handler:
            raise UnhandledActionException(f"Unhandled action: {event}.{action}")

        return action_handler(request)
