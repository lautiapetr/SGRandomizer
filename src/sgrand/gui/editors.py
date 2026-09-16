"""Guided, lossless editors for the versioned randomizer configuration."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from PySide6.QtCore import Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..errors import RandomizerError


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    minimum: int | None = None
    maximum: int | None = None
    suffix: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    help_text: str = ""


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "description")
    return label


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setWidget(widget)
    return area


def _describe(widget: QWidget, text: str, *, name: str = "") -> None:
    """Expose the same concise help to mouse, keyboard and assistive technology users."""
    widget.setToolTip(text)
    widget.setStatusTip(text)
    widget.setAccessibleDescription(text)
    if name:
        widget.setAccessibleName(name)


def _add_help_row(form: QFormLayout, label: str, widget: QWidget, help_text: str) -> None:
    label_widget = QLabel(label)
    label_widget.setBuddy(widget)
    _describe(label_widget, help_text)
    _describe(widget, help_text, name=label)
    form.addRow(label_widget, widget)


class StringListEditor(QWidget):
    """One-entry-per-line editor used for constants and source filenames."""

    changed = Signal()

    def __init__(self, placeholder: str, *, help_text: str, height: int = 100) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(placeholder)
        self.text.setMaximumHeight(height)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        _describe(self, help_text)
        _describe(self.text, help_text)
        self.text.textChanged.connect(self.changed)
        layout.addWidget(self.text)

    def set_values(self, values: list[str]) -> None:
        self.text.setPlainText("\n".join(values))

    def values(self) -> list[str]:
        return [line.strip() for line in self.text.toPlainText().splitlines() if line.strip()]


class FieldsGroup(QGroupBox):
    """A compact schema-driven group of booleans, numbers and choices."""

    changed = Signal()

    def __init__(
        self,
        title: str,
        specs: tuple[FieldSpec, ...],
        *,
        checkable: bool = False,
        description: str = "",
    ) -> None:
        super().__init__(title)
        self.specs = specs
        self.controls: dict[str, QWidget] = {}
        self.setCheckable(checkable)
        if description:
            self.setToolTip(description)
            self.setAccessibleDescription(description)
        form = QFormLayout(self)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        if description:
            form.addRow(_heading(description))
        for spec in specs:
            control: QWidget
            if spec.choices:
                combo = QComboBox()
                for choice_label, value in spec.choices:
                    combo.addItem(choice_label, value)
                combo.currentIndexChanged.connect(self.changed)
                control = combo
            elif spec.minimum is not None and spec.maximum is not None:
                spin = QSpinBox()
                spin.setRange(spec.minimum, spec.maximum)
                spin.setSuffix(spec.suffix)
                spin.valueChanged.connect(self.changed)
                control = spin
            else:
                checkbox = QCheckBox()
                checkbox.toggled.connect(self.changed)
                control = checkbox
            if spec.help_text:
                _describe(control, spec.help_text, name=spec.label)
            control.setObjectName(spec.key)
            self.controls[spec.key] = control
            field_label = QLabel(spec.label)
            field_label.setBuddy(control)
            _describe(field_label, spec.help_text)
            form.addRow(field_label, control)
        if checkable:
            self.toggled.connect(self.changed)

    def add_row(self, label: str, widget: QWidget, help_text: str = "") -> None:
        layout = cast(QFormLayout, self.layout())
        if not label:
            layout.addRow("", widget)
            return
        label_widget = QLabel(label)
        label_widget.setBuddy(widget)
        _describe(label_widget, help_text)
        if help_text and not widget.toolTip():
            _describe(widget, help_text, name=label)
        layout.addRow(label_widget, widget)

    def set_values(self, values: Mapping[str, Any]) -> None:
        if self.isCheckable():
            self.setChecked(bool(values["enabled"]))
        for spec in self.specs:
            value = values[spec.key]
            control = self.controls[spec.key]
            if isinstance(control, QComboBox):
                index = control.findData(value)
                if index < 0:
                    raise RandomizerError(f"Valor no soportado en {spec.key}: {value!r}")
                control.setCurrentIndex(index)
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QCheckBox):
                control.setChecked(bool(value))

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.isCheckable():
            result["enabled"] = self.isChecked()
        for spec in self.specs:
            control = self.controls[spec.key]
            if isinstance(control, QComboBox):
                result[spec.key] = control.currentData()
            elif isinstance(control, QSpinBox):
                result[spec.key] = control.value()
            elif isinstance(control, QCheckBox):
                result[spec.key] = control.isChecked()
        return result

    def control(self, key: str) -> QWidget:
        return self.controls[key]


class AdvancedJsonDialog(QDialog):
    """Escape hatch for exact, lossless editing of a subsystem document."""

    def __init__(
        self,
        parent: QWidget,
        title: str,
        document: dict[str, Any],
        validator: Callable[[dict[str, Any]], None],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"JSON avanzado — {title}")
        self.resize(850, 680)
        self._validator = validator
        self.result_document: dict[str, Any] | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(
            _heading(
                "Este modo expone el documento versionado completo. Al aceptar se valida "
                "con las mismas reglas que usa el motor y el formulario se sincroniza."
            )
        )
        self.editor = QPlainTextEdit(json.dumps(document, ensure_ascii=False, indent=2))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.editor, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_document)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept_document(self) -> None:
        try:
            raw = json.loads(self.editor.toPlainText())
            if not isinstance(raw, dict):
                raise RandomizerError("La raíz del JSON debe ser un objeto.")
            document = cast(dict[str, Any], raw)
            self._validator(document)
        except (json.JSONDecodeError, RandomizerError) as exc:
            QMessageBox.critical(self, "Configuración inválida", str(exc))
            return
        self.result_document = document
        self.accept()


class ConfigEditor(QWidget):
    """Base widget shared by guided subsystem editors."""

    changed = Signal()
    advanced_requested = Signal()

    def __init__(self, summary: str) -> None:
        super().__init__()
        self._loading = False
        self.root_layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(_heading(summary), 1)
        advanced = QPushButton("Opciones avanzadas…")
        _describe(
            advanced,
            "Edita todas las claves del documento versionado directamente. Recomendado solo "
            "si necesitas una opción que el formulario guiado no expone.",
        )
        advanced.clicked.connect(self.advanced_requested)
        header.addWidget(advanced)
        self.root_layout.addLayout(header)

    def _notify(self) -> None:
        if not self._loading:
            self.changed.emit()


LEARNSET_FIELDS = (
    FieldSpec(
        "offensive_percent",
        "Ataques que hacen daño",
        0,
        100,
        " %",
        help_text="Porcentaje aproximado de ataques ofensivos entre los movimientos aprendidos. "
        "Súbelo para Pokémon más directos; bájalo para incluir más estado y apoyo.",
    ),
    FieldSpec(
        "stab_percent",
        "Ataques del mismo tipo (STAB)",
        0,
        100,
        " %",
        help_text="Probabilidad de elegir un ataque que comparta tipo con el Pokémon. Valores "
        "altos hacen que aproveche más el bono de daño STAB.",
    ),
    FieldSpec(
        "category_match_percent",
        "Usar su mejor estadística ofensiva",
        0,
        100,
        " %",
        help_text="Probabilidad de dar ataques físicos a Pokémon con más Ataque y especiales "
        "a los que tienen más Ataque Especial. Súbelo para sets más eficaces.",
    ),
    FieldSpec(
        "minimum_accuracy",
        "Precisión mínima",
        1,
        100,
        " %",
        help_text="Descarta ataques cuya precisión sea menor. 70 permite riesgo; 90-100 crea "
        "learnsets mucho más fiables.",
    ),
    FieldSpec(
        "preserve_signature_moves",
        "Conservar movimientos característicos",
        help_text="Mantiene los movimientos emblemáticos en sus especies originales en vez de "
        "reemplazarlos durante la randomización.",
    ),
    FieldSpec(
        "early_attack_level",
        "Garantizar un ataque antes del nivel",
        1,
        20,
        help_text="Asegura que cada Pokémon aprenda al menos un movimiento que haga daño antes "
        "o en este nivel, evitando comienzos imposibles.",
    ),
)
COMPATIBILITY_FIELDS = (
    FieldSpec(
        "tm_percent",
        "Probabilidad base de aprender una MT",
        0,
        100,
        " %",
        help_text="Probabilidad inicial de que un Pokémon pueda aprender cada MT (TM en el "
        "código). Súbela para más libertad; bájala para decisiones más exigentes.",
    ),
    FieldSpec(
        "tutor_percent",
        "Probabilidad base de aprender de tutor",
        0,
        100,
        " %",
        help_text="Probabilidad inicial de aprender cada movimiento de tutor. Es independiente "
        "de la compatibilidad con MT.",
    ),
    FieldSpec(
        "stab_bonus_percent",
        "Bonificación si coincide el tipo",
        0,
        100,
        " %",
        help_text="Probabilidad adicional de compatibilidad cuando el movimiento comparte tipo "
        "con el Pokémon. Favorece opciones temáticas y útiles.",
    ),
    FieldSpec(
        "category_match_bonus_percent",
        "Bonificación si aprovecha su mejor ataque",
        0,
        100,
        " %",
        help_text="Probabilidad adicional para movimientos físicos o especiales que aprovechen "
        "la estadística ofensiva más alta del Pokémon.",
    ),
    FieldSpec(
        "preserve_protected_moves",
        "Conservar movimientos necesarios para progresar",
        help_text="Mantiene compatibilidad con Surf, Corte y otros movimientos necesarios para "
        "avanzar. Esta protección no puede desactivarse en una configuración válida.",
    ),
    FieldSpec(
        "preserve_signature_moves",
        "Conservar compatibilidad característica",
        help_text="Evita que las especies originales pierdan acceso a sus movimientos "
        "característicos mediante MT o tutor.",
    ),
)
PROPERTY_FIELDS = (
    FieldSpec(
        "power_variation_percent",
        "Cuánto puede variar la potencia",
        0,
        100,
        " %",
        help_text="Límite porcentual de cambio respecto a la potencia original. 0 conserva la "
        "potencia; valores altos producen ataques mucho más impredecibles.",
    ),
    FieldSpec(
        "minimum_power",
        "Potencia mínima posible",
        1,
        250,
        help_text="Ningún ataque ofensivo randomizado quedará por debajo de esta potencia.",
    ),
    FieldSpec(
        "maximum_power",
        "Potencia máxima posible",
        1,
        250,
        help_text="Ningún ataque ofensivo randomizado superará esta potencia. Bájala para "
        "reducir golpes excesivamente fuertes.",
    ),
    FieldSpec(
        "power_step",
        "Incrementos de potencia",
        1,
        50,
        help_text="Redondea la potencia a múltiplos de este valor. 5 produce cifras típicas de "
        "Pokémon; 1 permite cualquier número.",
    ),
    FieldSpec(
        "minimum_accuracy",
        "Precisión mínima posible",
        1,
        100,
        " %",
        help_text="Límite inferior para la nueva precisión de los movimientos.",
    ),
    FieldSpec(
        "maximum_accuracy",
        "Precisión máxima posible",
        1,
        100,
        " %",
        help_text="Límite superior para la nueva precisión. 100 permite ataques que nunca fallan "
        "por precisión normal.",
    ),
    FieldSpec(
        "accuracy_step",
        "Incrementos de precisión",
        1,
        25,
        help_text="Redondea la precisión a saltos de este tamaño; por ejemplo, 5 genera 70, 75, "
        "80, etc.",
    ),
    FieldSpec(
        "minimum_pp",
        "PP mínimos",
        1,
        64,
        help_text="Cantidad mínima de usos que puede recibir un movimiento.",
    ),
    FieldSpec(
        "maximum_pp",
        "PP máximos",
        1,
        64,
        help_text="Cantidad máxima de usos. Valores altos hacen más fácil conservar ataques "
        "fuertes durante rutas largas.",
    ),
    FieldSpec(
        "pp_step",
        "Incrementos de PP",
        1,
        20,
        help_text="Redondea los PP a múltiplos de este valor. 5 se parece al reparto habitual.",
    ),
    FieldSpec(
        "randomize_type",
        "Cambiar el tipo de los movimientos",
        help_text="Permite que un movimiento pase a ser Fuego, Agua, Planta, etc. Los tipos se "
        "eligen de la lista permitida de esta sección.",
    ),
    FieldSpec(
        "randomize_category",
        "Cambiar entre físico, especial y estado",
        help_text="Permite cambiar la categoría de daño. Los efectos internos del movimiento "
        "siguen siendo los originales.",
    ),
)


class MoveConfigEditor(ConfigEditor):
    def __init__(self) -> None:
        super().__init__(
            "Elige qué aprende cada Pokémon, qué MT puede usar y cómo se comportan sus "
            "movimientos. Los efectos especiales siempre se conservan."
        )
        self._document: dict[str, Any] = {}
        tabs = QTabWidget()
        self.root_layout.addWidget(tabs, 1)

        global_page = QWidget()
        global_form = QFormLayout(global_page)
        self.profile = QLineEdit()
        self.profile.textChanged.connect(self._notify)
        self.protected = StringListEditor(
            "MOVE_SURF\nMOVE_CUT",
            help_text="Un movimiento por línea, usando su constante MOVE_. Nunca se reemplazan "
            "ni se pierde su compatibilidad: aquí deben estar los necesarios para eventos o "
            "progresión. Las protecciones obligatorias no pueden quitarse.",
        )
        self.signature = StringListEditor(
            "MOVE_V_CREATE",
            help_text="Movimientos emblemáticos asociados a especies concretas, uno por línea. "
            "Se conservan al activar la opción correspondiente en movimientos o compatibilidad.",
        )
        self.excluded = StringListEditor(
            "MOVE_NONE\nMOVE_STRUGGLE",
            help_text="Movimientos que nunca podrán ser elegidos como resultado aleatorio, uno "
            "por línea. Úsala para retirar movimientos rotos, inútiles o que no quieras ver.",
        )
        for editor in (self.protected, self.signature, self.excluded):
            editor.changed.connect(self._notify)
        _add_help_row(
            global_form,
            "Nombre de esta configuración",
            self.profile,
            "Nombre guardado dentro del archivo de configuración. Sirve para identificarlo; no "
            "cambia por sí solo ninguna regla del randomizador.",
        )
        _add_help_row(
            global_form,
            "Movimientos protegidos (progresión)",
            self.protected,
            self.protected.toolTip(),
        )
        _add_help_row(
            global_form,
            "Movimientos característicos",
            self.signature,
            self.signature.toolTip(),
        )
        _add_help_row(global_form, "Movimientos excluidos", self.excluded, self.excluded.toolTip())
        index = tabs.addTab(_scroll(global_page), "Protecciones")
        tabs.setTabToolTip(
            index, "Edita las listas especiales que limitan la randomización de movimientos."
        )

        learn_page = QWidget()
        learn_layout = QVBoxLayout(learn_page)
        self.learnsets = FieldsGroup(
            "Cambiar movimientos aprendidos por nivel",
            LEARNSET_FIELDS,
            checkable=True,
            description="Activa esta sección para cambiar qué aprende cada Pokémon al subir de "
            "nivel. La potencia progresiva evita ataques desproporcionados al comienzo.",
        )
        self.learnsets.changed.connect(self._notify)
        self.source_files = StringListEditor(
            "gen_9.h\ngen_7.h",
            help_text="Archivos de generación usados como fuentes de movimientos, uno por línea "
            "(por ejemplo, gen_9.h). Una fuente desconocida se rechaza al validar.",
            height=70,
        )
        self.source_files.changed.connect(self._notify)
        self.learnsets.add_row(
            "Fuentes de movimientos", self.source_files, self.source_files.toolTip()
        )
        self.power_table = QTableWidget(0, 3)
        self.power_table.setHorizontalHeaderLabels(("Hasta nivel", "Potencia mínima", "Máxima"))
        self.power_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.power_table.setMinimumHeight(170)
        self.power_table.itemChanged.connect(self._notify)
        power_help = (
            "Cada fila define la potencia mínima y máxima permitida hasta cierto nivel. Ordena "
            "los niveles de menor a mayor y termina en 100; tramos tempranos bajos producen una "
            "progresión más parecida a una partida normal."
        )
        _describe(self.power_table, power_help, name="Fuerza progresiva")
        table_actions = QWidget()
        table_layout = QHBoxLayout(table_actions)
        table_layout.setContentsMargins(0, 0, 0, 0)
        add_band = QPushButton("Añadir tramo")
        remove_band = QPushButton("Quitar tramo")
        _describe(add_band, "Añade una nueva fila a la tabla de fuerza progresiva.")
        _describe(
            remove_band,
            "Quita la fila seleccionada; si no hay selección, quita la última.",
        )
        add_band.clicked.connect(self._add_power_band)
        remove_band.clicked.connect(self._remove_power_band)
        table_layout.addWidget(add_band)
        table_layout.addWidget(remove_band)
        table_layout.addStretch(1)
        self.learnsets.add_row("Potencia según el nivel", self.power_table, power_help)
        self.learnsets.add_row("", table_actions)
        learn_layout.addWidget(self.learnsets)
        learn_layout.addStretch(1)
        index = tabs.addTab(_scroll(learn_page), "Por nivel")
        tabs.setTabToolTip(
            index, "Configura los movimientos que cada especie aprende al subir de nivel."
        )

        compatibility_page = QWidget()
        compatibility_layout = QVBoxLayout(compatibility_page)
        self.compatibility = FieldsGroup(
            "Cambiar compatibilidad con MT y tutores",
            COMPATIBILITY_FIELDS,
            checkable=True,
            description="Activa esta sección para cambiar qué especies aceptan cada MT y cada "
            "tutor. Los movimientos necesarios para avanzar siguen protegidos.",
        )
        self.compatibility.changed.connect(self._notify)
        compatibility_layout.addWidget(self.compatibility)
        compatibility_layout.addStretch(1)
        index = tabs.addTab(_scroll(compatibility_page), "MT y tutores")
        tabs.setTabToolTip(
            index, "Configura qué Pokémon pueden aprender movimientos mediante MT o tutores."
        )

        properties_page = QWidget()
        properties_layout = QVBoxLayout(properties_page)
        self.properties = FieldsGroup(
            "Cambiar datos de los movimientos",
            PROPERTY_FIELDS,
            checkable=True,
            description="Activa esta sección para modificar potencia, precisión, PP, tipo y "
            "categoría. El efecto interno de cada movimiento nunca se toca.",
        )
        self.properties.changed.connect(self._notify)
        self.types = StringListEditor(
            "TYPE_FIRE\nTYPE_WATER",
            help_text="Tipos que podrán recibir los movimientos, uno por línea usando constantes "
            "TYPE_. La lista no puede quedar vacía si se randomiza el tipo.",
            height=130,
        )
        self.types.changed.connect(self._notify)
        self.properties.add_row("Tipos permitidos", self.types, self.types.toolTip())
        properties_layout.addWidget(self.properties)
        properties_layout.addStretch(1)
        index = tabs.addTab(_scroll(properties_page), "Potencia, tipo y PP")
        tabs.setTabToolTip(
            index,
            "Ajusta números y categoría de los movimientos sin alterar sus efectos internos.",
        )

    def _add_power_band(self) -> None:
        row = self.power_table.rowCount()
        self.power_table.insertRow(row)
        defaults = (100 if row == 0 else min(100, row * 25), 20, 80)
        for column, value in enumerate(defaults):
            self.power_table.setItem(row, column, QTableWidgetItem(str(value)))
        self._notify()

    def _remove_power_band(self) -> None:
        row = self.power_table.currentRow()
        if row < 0:
            row = self.power_table.rowCount() - 1
        if row >= 0:
            self.power_table.removeRow(row)
            self._notify()

    def set_document(self, document: dict[str, Any]) -> None:
        self._loading = True
        try:
            self._document = copy.deepcopy(document)
            self.profile.setText(str(document["profile"]))
            self.protected.set_values(cast(list[str], document["protected_moves"]))
            self.signature.set_values(cast(list[str], document["signature_moves"]))
            self.excluded.set_values(cast(list[str], document["excluded_moves"]))
            learnsets = cast(dict[str, Any], document["learnsets"])
            self.learnsets.set_values(learnsets)
            self.source_files.set_values(cast(list[str], learnsets["source_files"]))
            self.power_table.setRowCount(0)
            for band in cast(list[dict[str, int]], learnsets["progressive_power"]):
                row = self.power_table.rowCount()
                self.power_table.insertRow(row)
                for column, key in enumerate(("through_level", "minimum", "maximum")):
                    self.power_table.setItem(row, column, QTableWidgetItem(str(band[key])))
            self.compatibility.set_values(cast(dict[str, Any], document["compatibility"]))
            properties = cast(dict[str, Any], document["properties"])
            self.properties.set_values(properties)
            self.types.set_values(cast(list[str], properties["types"]))
        finally:
            self._loading = False

    def document(self) -> dict[str, Any]:
        document = copy.deepcopy(self._document)
        document["profile"] = self.profile.text().strip()
        document["protected_moves"] = self.protected.values()
        document["signature_moves"] = self.signature.values()
        document["excluded_moves"] = self.excluded.values()
        learnsets = self.learnsets.values()
        learnsets["source_files"] = self.source_files.values()
        bands: list[dict[str, int]] = []
        for row in range(self.power_table.rowCount()):
            try:
                cells = [self.power_table.item(row, column) for column in range(3)]
                if any(cell is None for cell in cells):
                    raise ValueError
                values = [int(cast(QTableWidgetItem, cell).text()) for cell in cells]
            except ValueError as exc:
                raise RandomizerError(
                    f"El tramo {row + 1} de fuerza progresiva contiene un valor inválido."
                ) from exc
            bands.append({"through_level": values[0], "minimum": values[1], "maximum": values[2]})
        learnsets["progressive_power"] = bands
        document["learnsets"] = learnsets
        document["compatibility"] = self.compatibility.values()
        properties = self.properties.values()
        properties["types"] = self.types.values()
        document["properties"] = properties
        return document


ABILITY_FIELDS = (
    FieldSpec(
        "follow_evolutions",
        "Mantener coherencia al evolucionar",
        help_text="Hace que una familia evolutiva conserve una progresión coherente de "
        "habilidades. Desactívalo si quieres que cada etapa sea totalmente independiente.",
    ),
    FieldSpec(
        "allow_duplicates",
        "Permitir habilidades repetidas",
        help_text="Permite repetir una habilidad entre los espacios principales o innatos de "
        "una especie. Desactivado ofrece más variedad dentro del mismo Pokémon.",
    ),
    FieldSpec(
        "rating_strategy",
        "Equilibrio de potencia",
        choices=(("Parecida a la original", "similar"), ("Completamente libre", "any")),
        help_text="«Parecida» busca habilidades con valoración semejante a la original. "
        "«Libre» ignora esa semejanza, aunque sigue respetando los límites mínimo y máximo.",
    ),
    FieldSpec(
        "minimum_ai_rating",
        "Potencia interna mínima",
        -20,
        20,
        help_text="Valoración interna mínima usada por SoulGold para medir utilidad. Valores "
        "más altos eliminan habilidades débiles o perjudiciales del conjunto.",
    ),
    FieldSpec(
        "maximum_ai_rating",
        "Potencia interna máxima",
        -20,
        20,
        help_text="Valoración interna máxima permitida. Bájala para evitar habilidades muy "
        "fuertes; súbela para ampliar el conjunto disponible.",
    ),
    FieldSpec(
        "maximum_rating_delta",
        "Diferencia máxima con la original",
        0,
        40,
        help_text="Cuando usas potencia parecida, limita cuánto puede alejarse la nueva "
        "habilidad de la valoración original. 0 exige la misma valoración.",
    ),
    FieldSpec(
        "allow_special_abilities",
        "Permitir habilidades excepcionalmente fuertes",
        help_text="Incluye habilidades especiales como Wonder Guard, Huge Power o Speed Boost. "
        "Actívalo para partidas más caóticas o difíciles de equilibrar.",
    ),
)
INNATE_FIELDS = (
    *ABILITY_FIELDS,
    FieldSpec(
        "count_mode",
        "Cantidad de innatas",
        choices=(("Conservar cantidad vanilla", "vanilla"), ("Cantidad fija", "fixed")),
        help_text="Conserva cuántas innatas tenía cada especie o fuerza la misma cantidad para "
        "todas. Las innatas nunca duplican una habilidad principal.",
    ),
    FieldSpec(
        "fixed_count",
        "Cantidad fija de innatas",
        0,
        3,
        help_text="Número de innatas asignadas a cada especie cuando eliges cantidad fija. 0 "
        "las desactiva de hecho; 3 ofrece la máxima variedad.",
    ),
)


class AbilityConfigEditor(ConfigEditor):
    def __init__(self) -> None:
        super().__init__(
            "Decide qué habilidades puede tener cada Pokémon. Las habilidades principales e "
            "innatas se sortean por separado y las formas especiales siguen protegidas."
        )
        self._document: dict[str, Any] = {}
        profile_bar = QHBoxLayout()
        profile_label = QLabel("Perfil de habilidades activo:")
        self.profile_combo = QComboBox()
        profile_help = (
            "Elige el conjunto de reglas que se aplicará. Balanced prioriza resultados "
            "razonables y Chaos permite combinaciones más extremas; cada perfil conserva "
            "sus cambios."
        )
        profile_label.setBuddy(self.profile_combo)
        _describe(profile_label, profile_help)
        _describe(self.profile_combo, profile_help, name="Perfil de habilidades activo")
        profile_bar.addWidget(profile_label)
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        profile_bar.addWidget(self.profile_combo)
        profile_bar.addStretch(1)
        self.root_layout.addLayout(profile_bar)
        tabs = QTabWidget()
        self.root_layout.addWidget(tabs, 1)

        normal_page = QWidget()
        normal_layout = QVBoxLayout(normal_page)
        self.normal = FieldsGroup(
            "Cambiar habilidades principales",
            ABILITY_FIELDS,
            checkable=True,
            description="Activa esta sección para cambiar las habilidades principales de cada "
            "especie. Las habilidades de formas y las no funcionales siguen protegidas.",
        )
        self.normal.changed.connect(self._notify)
        cast(QComboBox, self.normal.control("rating_strategy")).currentIndexChanged.connect(
            self._update_dependencies
        )
        normal_layout.addWidget(self.normal)
        normal_layout.addStretch(1)
        index = tabs.addTab(_scroll(normal_page), "Habilidades normales")
        tabs.setTabToolTip(index, "Reglas para las habilidades principales de cada especie.")

        innate_page = QWidget()
        innate_layout = QVBoxLayout(innate_page)
        self.innates = FieldsGroup(
            "Cambiar habilidades innatas",
            INNATE_FIELDS,
            checkable=True,
            description="Activa esta sección para cambiar las habilidades innatas adicionales. "
            "Nunca se repite aquí una habilidad principal y usa un RNG independiente.",
        )
        self.innates.changed.connect(self._notify)
        cast(QComboBox, self.innates.control("rating_strategy")).currentIndexChanged.connect(
            self._update_dependencies
        )
        cast(QComboBox, self.innates.control("count_mode")).currentIndexChanged.connect(
            self._update_dependencies
        )
        innate_layout.addWidget(self.innates)
        innate_layout.addStretch(1)
        index = tabs.addTab(_scroll(innate_page), "Innatas")
        tabs.setTabToolTip(
            index, "Reglas para las habilidades innatas adicionales de cada especie."
        )

        protection_page = QWidget()
        protection_form = QFormLayout(protection_page)
        self.blacklist = StringListEditor(
            "ABILITY_TRUANT",
            help_text="Habilidades que nunca se asignarán al azar, una constante ABILITY_ por "
            "línea. Úsala para retirar habilidades molestas o incompatibles con tu partida.",
        )
        self.locked = StringListEditor(
            "ABILITY_MULTITYPE",
            help_text="Habilidades reservadas para especies o formas concretas, una por línea. "
            "El motor conserva las protecciones obligatorias aunque intentes quitarlas.",
            height=150,
        )
        self.special = StringListEditor(
            "ABILITY_WONDER_GUARD",
            help_text="Habilidades excepcionalmente fuertes o disruptivas, una por línea. Solo "
            "entran al conjunto si activas «Permitir habilidades excepcionalmente fuertes».",
            height=150,
        )
        for editor in (self.blacklist, self.locked, self.special):
            editor.changed.connect(self._notify)
        _add_help_row(
            protection_form, "Lista negra personalizada", self.blacklist, self.blacklist.toolTip()
        )
        _add_help_row(
            protection_form, "Protegidas por forma/especie", self.locked, self.locked.toolTip()
        )
        _add_help_row(
            protection_form, "Habilidades especiales", self.special, self.special.toolTip()
        )
        index = tabs.addTab(_scroll(protection_page), "Protecciones")
        tabs.setTabToolTip(
            index, "Controla qué habilidades se excluyen, se reservan o se consideran especiales."
        )

    @property
    def profile_name(self) -> str:
        return self.profile_combo.currentText()

    def _profiles(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._document["profiles"])

    def _store_profile(self, name: str) -> None:
        if name and name in self._profiles():
            self._profiles()[name] = {
                "abilities": self.normal.values(),
                "innates": self.innates.values(),
            }

    def _load_profile(self, name: str) -> None:
        profile = cast(dict[str, dict[str, Any]], self._profiles()[name])
        self.normal.set_values(profile["abilities"])
        self.innates.set_values(profile["innates"])
        self._update_dependencies()

    def _update_dependencies(self) -> None:
        for panel in (self.normal, self.innates):
            strategy = cast(QComboBox, panel.control("rating_strategy")).currentData()
            panel.control("maximum_rating_delta").setEnabled(strategy == "similar")
        count_mode = cast(QComboBox, self.innates.control("count_mode")).currentData()
        self.innates.control("fixed_count").setEnabled(count_mode == "fixed")

    def _switch_profile(self, name: str) -> None:
        if self._loading or not name:
            return
        previous = str(self._document.get("default_profile", ""))
        if previous in self._profiles():
            self._store_profile(previous)
        self._document["default_profile"] = name
        self._loading = True
        try:
            self._load_profile(name)
        finally:
            self._loading = False
        self.changed.emit()

    def set_document(self, document: dict[str, Any], profile_name: str) -> None:
        self._loading = True
        try:
            self._document = copy.deepcopy(document)
            profiles = self._profiles()
            if profile_name not in profiles:
                raise RandomizerError(f"Perfil de habilidades desconocido: {profile_name!r}")
            self._document["default_profile"] = profile_name
            self.profile_combo.clear()
            self.profile_combo.addItems(list(profiles))
            self.profile_combo.setCurrentText(profile_name)
            self._load_profile(profile_name)
            self.blacklist.set_values(cast(list[str], document["blacklist"]))
            self.locked.set_values(cast(list[str], document["species_locked_abilities"]))
            self.special.set_values(cast(list[str], document["special_abilities"]))
        finally:
            self._loading = False

    def document(self) -> dict[str, Any]:
        self._store_profile(self.profile_name)
        self._document["default_profile"] = self.profile_name
        self._document["blacklist"] = self.blacklist.values()
        self._document["species_locked_abilities"] = self.locked.values()
        self._document["special_abilities"] = self.special.values()
        return copy.deepcopy(self._document)


LEVEL_CHOICES = (("Conservar niveles", "vanilla"), ("Escalar", "scaled"), ("Fijo", "fixed"))
TEAM_CHOICES = (("Conservar tamaño", "vanilla"), ("Fijo", "fixed"), ("Rango", "range"))
THEME_CHOICES = (("Sin tema", "none"), ("Tipo vanilla", "vanilla"), ("Tipo aleatorio", "random"))
MOVE_CHOICES = (("Conservar", "preserve"), ("Movimientos legales", "legal"))
ITEM_CHOICES = (("Conservar", "preserve"), ("Aleatorios", "random"), ("Sin objetos", "none"))
TRAINER_FIELDS = (
    FieldSpec(
        "maximum_bst_delta",
        "Margen de fuerza del Pokémon (BST)",
        0,
        2000,
        help_text="Diferencia máxima de estadísticas base totales respecto al Pokémon original. "
        "Un valor bajo conserva la dificultad; uno alto permite reemplazos mucho más fuertes "
        "o débiles.",
    ),
    FieldSpec(
        "level_mode",
        "Cómo ajustar los niveles",
        choices=LEVEL_CHOICES,
        help_text="Conserva los niveles originales, escálalos por porcentaje o fija el mismo "
        "nivel para todos los Pokémon de esta categoría.",
    ),
    FieldSpec(
        "level_percent",
        "Multiplicador de nivel",
        1,
        500,
        " %",
        help_text="Se usa en modo Escalar. 100 % conserva el nivel, 110 % lo aumenta un 10 % y "
        "90 % lo reduce un 10 %.",
    ),
    FieldSpec(
        "level_offset",
        "Niveles extra después de escalar",
        -99,
        99,
        help_text="Se suma después del porcentaje en modo Escalar. Usa +2 para añadir dos "
        "niveles o -2 para quitarlos.",
    ),
    FieldSpec(
        "fixed_level",
        "Nivel fijo",
        1,
        100,
        help_text="Nivel asignado a todos los Pokémon cuando el modo elegido es Fijo.",
    ),
    FieldSpec(
        "minimum_level",
        "Nivel mínimo permitido",
        1,
        100,
        help_text="Evita que el ajuste produzca Pokémon por debajo de este nivel.",
    ),
    FieldSpec(
        "maximum_level",
        "Nivel máximo permitido",
        1,
        100,
        help_text="Evita que el ajuste produzca Pokémon por encima de este nivel.",
    ),
    FieldSpec(
        "team_size_mode",
        "Cómo decidir el tamaño del equipo",
        choices=TEAM_CHOICES,
        help_text="Conserva la cantidad original, usa una cantidad fija o elige al azar dentro "
        "de un rango.",
    ),
    FieldSpec(
        "fixed_team_size",
        "Cantidad fija de Pokémon",
        1,
        6,
        help_text="Cantidad exacta de Pokémon por entrenador cuando el tamaño es Fijo.",
    ),
    FieldSpec(
        "minimum_team_size",
        "Cantidad mínima de Pokémon",
        1,
        6,
        help_text="Límite inferior cuando el tamaño del equipo se elige dentro de un rango.",
    ),
    FieldSpec(
        "maximum_team_size",
        "Cantidad máxima de Pokémon",
        1,
        6,
        help_text="Límite superior cuando el tamaño del equipo se elige dentro de un rango.",
    ),
    FieldSpec(
        "theme_mode",
        "Tema de tipos del equipo",
        choices=THEME_CHOICES,
        help_text="Sin tema mezcla tipos; Tipo vanilla conserva el estilo original; Tipo "
        "aleatorio elige una temática nueva para el entrenador.",
    ),
    FieldSpec(
        "theme_percent",
        "Probabilidad de usar el tema",
        0,
        100,
        " %",
        help_text="Probabilidad de que el entrenador respete el tema elegido. 100 % crea equipos "
        "siempre temáticos; valores menores permiten excepciones.",
    ),
    FieldSpec(
        "moves_mode",
        "Movimientos del equipo",
        choices=MOVE_CHOICES,
        help_text="Conservar mantiene el set competitivo original cuando sea posible. "
        "Movimientos legales crea un set que la nueva especie puede aprender.",
    ),
    FieldSpec(
        "held_items_mode",
        "Objetos equipados",
        choices=ITEM_CHOICES,
        help_text="Conserva los objetos originales, asigna objetos aleatorios o elimina todos "
        "los objetos equipados de esta categoría.",
    ),
    FieldSpec(
        "held_item_percent",
        "Probabilidad de llevar objeto",
        0,
        100,
        " %",
        help_text="En modo Aleatorios, decide con qué frecuencia cada Pokémon recibe un objeto "
        "equipado.",
    ),
    FieldSpec(
        "allow_legendaries",
        "Permitir Pokémon legendarios",
        help_text="Incluye legendarios y otras especies especiales en esta categoría de "
        "entrenadores. Puede aumentar mucho la dificultad.",
    ),
    FieldSpec(
        "legendary_percent",
        "Probabilidad de elegir un legendario",
        0,
        100,
        " %",
        help_text="Cuando los legendarios están permitidos, controla la probabilidad de intentar "
        "usar uno en cada selección.",
    ),
    FieldSpec(
        "allow_duplicates",
        "Permitir especies repetidas",
        help_text="Permite que un entrenador tenga dos o más Pokémon de la misma especie.",
    ),
    FieldSpec(
        "double_synergy",
        "Preparar equipos para combates dobles",
        help_text="Favorece combinaciones de tipos y movimientos de apoyo que funcionan juntas "
        "en combates dobles.",
    ),
)
TRAINER_LABELS = {
    "trainers": "Entrenadores",
    "leaders": "Líderes",
    "rival": "Rival",
    "bosses": "Jefes",
}


class TrainerConfigEditor(ConfigEditor):
    def __init__(self) -> None:
        super().__init__(
            "Crea equipos nuevos sin perder la dificultad esperada. Puedes personalizar por "
            "separado entrenadores, líderes, rival y jefes."
        )
        self._document: dict[str, Any] = {}
        profile_bar = QHBoxLayout()
        profile_label = QLabel("Perfil de entrenadores activo:")
        self.profile_combo = QComboBox()
        profile_help = (
            "Elige el conjunto de reglas aplicado a todos los grupos de entrenadores. Cada "
            "perfil conserva por separado los ajustes que hagas."
        )
        profile_label.setBuddy(self.profile_combo)
        _describe(profile_label, profile_help)
        _describe(self.profile_combo, profile_help, name="Perfil de entrenadores activo")
        profile_bar.addWidget(profile_label)
        self.profile_combo.currentTextChanged.connect(self._switch_profile)
        profile_bar.addWidget(self.profile_combo)
        profile_bar.addStretch(1)
        self.root_layout.addLayout(profile_bar)
        tabs = QTabWidget()
        self.root_layout.addWidget(tabs, 1)
        self.rules: dict[str, FieldsGroup] = {}
        category_help = {
            "trainers": "Entrenadores comunes encontrados durante rutas y edificios.",
            "leaders": "Líderes de gimnasio; puedes darles reglas más exigentes y temáticas.",
            "rival": "Combates del rival. La coherencia con el starter se preserva "
            "automáticamente.",
            "bosses": "Alto Mando, Campeón y las clases adicionales indicadas en Listas globales.",
        }
        for category, label in TRAINER_LABELS.items():
            page = QWidget()
            layout = QVBoxLayout(page)
            panel = FieldsGroup(
                f"Cambiar equipos de {label.lower()}",
                TRAINER_FIELDS,
                checkable=True,
                description=f"{category_help[category]} Desmarca el grupo para conservar sus "
                "equipos originales sin randomizar.",
            )
            panel.changed.connect(self._notify)
            self.rules[category] = panel
            for key in ("level_mode", "team_size_mode", "theme_mode", "held_items_mode"):
                cast(QComboBox, panel.control(key)).currentIndexChanged.connect(
                    lambda _index, selected=category: self._update_dependencies(selected)
                )
            cast(QCheckBox, panel.control("allow_legendaries")).toggled.connect(
                lambda _checked, selected=category: self._update_dependencies(selected)
            )
            layout.addWidget(panel)
            layout.addStretch(1)
            index = tabs.addTab(_scroll(page), label)
            tabs.setTabToolTip(index, category_help[category])

        global_page = QWidget()
        global_form = QFormLayout(global_page)
        self.blacklist_species = StringListEditor(
            "SPECIES_MEW",
            help_text="Especies que nunca aparecerán en equipos randomizados, una constante "
            "SPECIES_ por línea.",
        )
        self.blacklist_moves = StringListEditor(
            "MOVE_METRONOME",
            help_text="Movimientos que nunca se asignarán a los sets legales de entrenadores, "
            "una constante MOVE_ por línea.",
        )
        self.blacklist_items = StringListEditor(
            "ITEM_MASTER_BALL",
            help_text="Objetos que nunca se equiparán al azar, una constante ITEM_ por línea.",
        )
        self.item_allowlist = StringListEditor(
            "ITEM_LEFTOVERS",
            help_text="Si contiene entradas, los objetos aleatorios se eligen únicamente de "
            "esta lista. Déjala vacía para usar todo el conjunto válido no excluido.",
        )
        self.boss_classes = StringListEditor(
            "Elite Four\nChampion",
            help_text="Nombres de clases de entrenador que recibirán las reglas de Jefes, uno "
            "por línea. Deben coincidir con los nombres usados por SoulGold.",
            height=130,
        )
        for editor in (
            self.blacklist_species,
            self.blacklist_moves,
            self.blacklist_items,
            self.item_allowlist,
            self.boss_classes,
        ):
            editor.changed.connect(self._notify)
        for label, editor in (
            ("Especies excluidas", self.blacklist_species),
            ("Movimientos excluidos", self.blacklist_moves),
            ("Objetos excluidos", self.blacklist_items),
            ("Lista permitida de objetos", self.item_allowlist),
            ("Clases tratadas como bosses", self.boss_classes),
        ):
            _add_help_row(global_form, label, editor, editor.toolTip())
        index = tabs.addTab(_scroll(global_page), "Listas globales")
        tabs.setTabToolTip(
            index, "Exclusiones y conjuntos permitidos compartidos por todos los entrenadores."
        )

    @property
    def profile_name(self) -> str:
        return self.profile_combo.currentText()

    def _profiles(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._document["profiles"])

    def _store_profile(self, name: str) -> None:
        if name and name in self._profiles():
            self._profiles()[name] = {
                category: panel.values() for category, panel in self.rules.items()
            }

    def _load_profile(self, name: str) -> None:
        profile = cast(dict[str, dict[str, Any]], self._profiles()[name])
        for category, panel in self.rules.items():
            panel.set_values(profile[category])
            self._update_dependencies(category)

    def _update_dependencies(self, category: str) -> None:
        panel = self.rules[category]
        level_mode = cast(QComboBox, panel.control("level_mode")).currentData()
        panel.control("level_percent").setEnabled(level_mode == "scaled")
        panel.control("level_offset").setEnabled(level_mode == "scaled")
        panel.control("fixed_level").setEnabled(level_mode == "fixed")
        team_mode = cast(QComboBox, panel.control("team_size_mode")).currentData()
        panel.control("fixed_team_size").setEnabled(team_mode == "fixed")
        panel.control("minimum_team_size").setEnabled(team_mode == "range")
        panel.control("maximum_team_size").setEnabled(team_mode == "range")
        theme_mode = cast(QComboBox, panel.control("theme_mode")).currentData()
        panel.control("theme_percent").setEnabled(theme_mode != "none")
        item_mode = cast(QComboBox, panel.control("held_items_mode")).currentData()
        panel.control("held_item_percent").setEnabled(item_mode == "random")
        allow_legendaries = cast(QCheckBox, panel.control("allow_legendaries")).isChecked()
        panel.control("legendary_percent").setEnabled(allow_legendaries)

    def _switch_profile(self, name: str) -> None:
        if self._loading or not name:
            return
        previous = str(self._document.get("default_profile", ""))
        if previous in self._profiles():
            self._store_profile(previous)
        self._document["default_profile"] = name
        self._loading = True
        try:
            self._load_profile(name)
        finally:
            self._loading = False
        self.changed.emit()

    def set_document(self, document: dict[str, Any], profile_name: str) -> None:
        self._loading = True
        try:
            self._document = copy.deepcopy(document)
            profiles = self._profiles()
            if profile_name not in profiles:
                raise RandomizerError(f"Perfil de entrenadores desconocido: {profile_name!r}")
            self._document["default_profile"] = profile_name
            self.profile_combo.clear()
            self.profile_combo.addItems(list(profiles))
            self.profile_combo.setCurrentText(profile_name)
            self._load_profile(profile_name)
            self.blacklist_species.set_values(cast(list[str], document["blacklist_species"]))
            self.blacklist_moves.set_values(cast(list[str], document["blacklist_moves"]))
            self.blacklist_items.set_values(cast(list[str], document["blacklist_items"]))
            self.item_allowlist.set_values(cast(list[str], document["held_item_allowlist"]))
            self.boss_classes.set_values(cast(list[str], document["boss_classes"]))
        finally:
            self._loading = False

    def document(self) -> dict[str, Any]:
        self._store_profile(self.profile_name)
        self._document["default_profile"] = self.profile_name
        self._document["blacklist_species"] = self.blacklist_species.values()
        self._document["blacklist_moves"] = self.blacklist_moves.values()
        self._document["blacklist_items"] = self.blacklist_items.values()
        self._document["held_item_allowlist"] = self.item_allowlist.values()
        self._document["boss_classes"] = self.boss_classes.values()
        return copy.deepcopy(self._document)
