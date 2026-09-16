"""In-application first-run tutorial."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QWizard, QWizardPage

TUTORIAL_STEPS = (
    (
        "Bienvenido a SGRand",
        "SGRand modifica un proyecto de código fuente compatible, no una ROM existente. "
        "El flujo seguro es: elegir el proyecto, configurar, revisar, randomizar y compilar.",
    ),
    (
        "1. Proyecto y resultados",
        "Selecciona un proyecto limpio de SoulGold v.1.1.4 o usa «Descargar proyecto». "
        "Elige también una carpeta de salida para la ROM y el reporte. Para probar otra "
        "semilla, empieza desde otro proyecto limpio.",
    ),
    (
        "2. Preset y opciones",
        "Vanilla+ realiza cambios conservadores; Balanced es la experiencia recomendada; "
        "Chaos amplía la variación. Cambiar cualquier control convierte el preset en Custom. "
        "Cada sección tiene Opciones avanzadas para ajustes exactos e importación/exportación.",
    ),
    (
        "3. Semilla y spoilers",
        "Una misma configuración y semilla produce el mismo resultado. Puedes escribir una "
        "semilla memorable o generar una aleatoria. «Sin spoilers» oculta los resultados "
        "detallados del preview, manifiesto y reporte.",
    ),
    (
        "4. Revisión y randomización",
        "Ver cambios valida y calcula el resultado sin escribir archivos. Después, Randomizar "
        "aplica la operación de forma transaccional: si algo falla, no queda una modificación "
        "parcial. Revisa la pestaña Vista previa antes de continuar.",
    ),
    (
        "5. Diagnóstico y compilación",
        "Comprobar revisa el proyecto y las dependencias sin instalar nada. Compilar juego se "
        "habilita lógicamente después de randomizar esa misma configuración y semilla. El "
        "progreso aparece abajo y los detalles quedan en Actividad.",
    ),
)


class TutorialWizard(QWizard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tutorial de SGRand")
        self.resize(680, 440)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage)
        self.setButtonText(QWizard.WizardButton.NextButton, "Siguiente")
        self.setButtonText(QWizard.WizardButton.BackButton, "Atrás")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Finalizar")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Cerrar")
        for title, body in TUTORIAL_STEPS:
            page = QWizardPage()
            page.setTitle(title)
            layout = QVBoxLayout(page)
            text = QLabel(body)
            text.setWordWrap(True)
            text.setMinimumWidth(500)
            layout.addWidget(text)
            layout.addStretch(1)
            self.addPage(page)
